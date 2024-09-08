'''
TODO
------
Decide whether to use http or websockets
Better error handling
Implement subtask finetuning
Set up litellm load balancing, retries, timeouts etc. https://docs.litellm.ai/docs/proxy/reliability
'''

from .main_repo_agent import MainRepoAgent
from .planner_agent import PlannerAgent
from .external_repo_agent import InitExternalRepoAgentError, ExternalRepoAgent
from . import utils
import re
from typing import AsyncGenerator, List, Dict, Optional
from strictjson import *
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

import argparse
import logging

import asyncio
import os
import signal
import platform
from distro import name as distro_name

import litellm

litellm.suppress_debug_info = True
litellm.set_verbose = False
litellm.drop_params = True


logging.basicConfig(level=logging.INFO)

app = FastAPI()


class Manager:
    """
    A class to manage the overall process and agents.
    """

    def __init__(self, model_name: str = "azure/gpt-4o",
                 max_reflections: int = 5) -> None:
        """
        Initialize the Manager.
        """
        self.planner_agent: Optional[PlannerAgent] = None
        self.main_repo_agent: Optional[MainRepoAgent] = None
        self.external_repo_agents: Dict[str, ExternalRepoAgent] = dict()
        self.logger = logging.getLogger("AgentManager")
        self.model_name = model_name
        self.max_reflections = max_reflections

        def _os_name() -> str:
            current_platform = platform.system()
            if current_platform == "Linux":
                return "Linux/" + distro_name(pretty=True)
            if current_platform == "Windows":
                return "Windows " + platform.release()
            if current_platform == "Darwin":
                return "Darwin/MacOS " + platform.mac_ver()[0]
            return current_platform

        def _shell_name() -> str:
            current_platform = platform.system()
            if current_platform in ("Windows", "nt"):
                is_powershell = len(
                    os.getenv(
                        "PSModulePath",
                        "").split(
                        os.pathsep)) >= 3
                return "powershell.exe" if is_powershell else "cmd.exe"
            return os.path.basename(os.getenv("SHELL", "/bin/sh"))

        self.os_name = _os_name()
        self.shell = _shell_name()

        self.completed_subtasks: List[str] = []

        self.init_planner_agent()
        self.init_main_repo_agent()

    def init_external_repo_agent(
            self,
            repo_dir: str,
            model_name: str = "azure/gpt-4o") -> str:
        """
        Initialize an Aider agent.

        :param repo_dir: The directory of the repository.
        :param model_name: The name of the model to use.
        :return: "success" if the agent is initialized, otherwise an error message.
        """
        repo_dir = utils.get_absolute_path(repo_dir)
        if repo_dir == utils.get_absolute_path("."):
            return "error: cannot initialize agent on current directory"
        if repo_dir in self.external_repo_agents:
            return "error: agent already initialized on this repo dir"

        try:
            agent = ExternalRepoAgent(model_name=model_name, repo_dir=repo_dir)
            self.external_repo_agents[repo_dir] = agent
            return "success"
        except InitExternalRepoAgentError as e:
            return str(e)

    def init_main_repo_agent(self, model_name: str = "azure/gpt-4o") -> str:
        """
        Initialize the main Aider agent.

        :param model_name: The name of the model to use.
        :return: "success" if the agent is initialized.
        """
        self.main_repo_agent = MainRepoAgent(model_name=model_name)
        return "success"

    def init_planner_agent(self, model_name: str = "azure/gpt-4o") -> str:
        """
        Initialize the Planner agent.

        :param model_name: The name of the model to use.
        :return: "success" if the agent is initialized.
        """
        self.planner_agent = PlannerAgent(model_name)
        return "success"

    async def generate_subtasks(self, objective: str) -> List[str]:
        """
        Generate a list of subtasks to achieve the given objective.

        :param objective: The main objective.
        :return: A list of subtasks.
        """
        return await self.planner_agent.generate_subtasks(objective)

    def finetune_subtasks(self, objective: str, instruction: str) -> List[str]:
        """
        Finetune the generated subtasks based on additional instructions.

        :param objective: The main objective.
        :param instruction: Additional instructions for finetuning.
        :return: A list of finetuned subtasks.
        """
        return "TODO"

    async def run_subtask(self, subtask: str) -> AsyncGenerator[str, None]:
        """
        Run a subtask using the main Aider agent.

        :param subtask: The subtask to run.
        :return: An async generator yielding parts of the response.
        """

        await asyncio.gather(*(external_repo_agent.find_relevant_code(subtask) for external_repo_agent in self.external_repo_agents.values()))

        for repo_path in self.external_repo_agents:
            code_snippet_filename = f"code_snippets_{repo_path.replace('/', '').replace('.','')}.txt"
            self.logger.info(f"found {code_snippet_filename}")
            try:
                self.main_repo_agent.run(f"/read-only {code_snippet_filename}")
            except BaseException:
                self.logger.warning(
                    f"{code_snippet_filename} not found, skipping")

        completed_tasks = ""

        if len(self.completed_subtasks) > 0:
            completed_tasks = "These are the tasks that you have already completed:\n"
            completed_tasks += "\n".join([f"{j+1}: {t}" for j,
                                          t in enumerate(self.completed_subtasks)])

        message = ""
        if len(self.completed_subtasks) > 0:
            message = f"""{completed_tasks}

Based on the above completed tasks, you are to complete the following task:
{subtask}

If the files you wish to write to do not exist yet, automatically create them.
"""
        else:
            message = f"""{completed_tasks}

You are to complete the following task:
{subtask}

If the files you wish to write to do not exist yet, automatically create them.
If you wish to edit a file, add the file to the chat.
"""
        response = ""
        for _ in range(self.max_reflections):
            curr_response = ""
            async for partial_response in self.main_repo_agent.run_stream(message):
                curr_response += partial_response
                yield partial_response

            response += curr_response

            # Check for shell commands and files to add in the response
            def check_for_shell_cmds_in_response(
                    aider_agent_response: str) -> Optional[List[str]]:
                """
                Check if there are shell commands in the Aider agent response.

                :param aider_agent_response: The response from the Aider agent.
                :return: The shell command if found, otherwise None.
                """
                # List of shell code block markers
                shell_markers = [
                    "bash", "sh", "shell", "cmd", "batch", "powershell", "ps1",
                    "zsh", "fish", "ksh", "csh", "tcsh"
                ]

                # Create a regex pattern to match any of the shell code block
                # markers
                shell_code_pattern = re.compile(
                    r'```(?:' + '|'.join(shell_markers) + r')(.*?)```',
                    re.DOTALL | re.IGNORECASE)

                # Find all matches
                matches = shell_code_pattern.findall(aider_agent_response)

                if not matches:
                    return None

                return matches

            # Check for shell commands and files to add in the response
            shell_cmds = check_for_shell_cmds_in_response(curr_response)

            if shell_cmds is not None:
                for command in shell_cmds:
                    yield f"\n<suggested_cmd>{command}</suggested_cmd>\n"
                    # Optionally, you can execute the command here if needed
                    # cmd_response = self.main_repo_agent.run_cmd(command)
                    # yield f"<cmd_response>{cmd_response}</cmd_response>"

            # Use the new function to find files to add

            if self.main_repo_agent.coder.reflected_message is None:
                break
            else:
                message = self.main_repo_agent.coder.reflected_message

        self.completed_subtasks.append(subtask)

    def undo_last_subtask(self) -> str:
        """
        Undo the last completed subtask.

        :return: The result of the undo operation.
        """
        if len(self.completed_subtasks):
            self.completed_subtasks.pop()
            result = self.main_repo_agent.run('/undo')
            return result
        else:
            return "error: no previously completed subtasks"

    async def confirm_run_subtasks(
            self, subtasks: List[str]) -> AsyncGenerator[str, None]:
        """
        Confirm and run the generated subtasks.

        :param subtasks: The list of subtasks to run.
        :return: An async generator yielding parts of the response.
        """

        responses = []
        for subtask in subtasks:
            response = ""
            async for partial_response in self.run_subtask(subtask):
                response += partial_response
                yield partial_response
            responses.append(response)

        # return responses

    def get_external_repo_agents(self) -> List[str]:
        """
        Get a list of all initialized Aider agents.

        :return: A list of initialized Aider agents.
        """
        return list(self.external_repo_agents.keys())

    def shutdown(self) -> str:
        """
        Shutdown all external repo agents.

        :return: "shutdown" after shutting down all agents.
        """
        for external_repo_agent in self.external_repo_agents.values():
            external_repo_agent.kill()
        return "shutdown"


manager = Manager()

# create agent


@app.post("/init_external_repo_agent")
async def init_external_repo_agent(repo_dir: str) -> str:
    """
    API endpoint to initialize an Aider agent.

    :param repo_dir: The directory of the repository.
    :return: The result of the initialization.
    """
    result = manager.init_external_repo_agent(repo_dir)
    return result


@app.get("/get_external_repo_agents")
async def get_external_repo_agents() -> List[str]:
    """
    API endpoint to get a list of all initialized Aider agents.

    :return: The result containing the list of agents.
    """
    return manager.get_external_repo_agents()

# generate subtasks


@app.post("/generate_subtasks")
async def generate_subtasks(objective: str) -> List[str]:
    """
    API endpoint to generate subtasks for a given objective.

    :param objective: The main objective.
    :return: The list of generated subtasks.
    """
    return await manager.generate_subtasks(objective)

# finetune subtasks


@app.post("/finetune_subtasks")
async def finetune_subtasks(objective: str, instruction: str) -> List[str]:
    """
    API endpoint to finetune the generated subtasks based on additional instructions.

    :param objective: The main objective.
    :param instruction: Additional instructions for finetuning.
    :return: The result of the finetuning.
    """
    return manager.finetune_subtasks(objective, instruction)


@app.post("/run_subtask")
async def run_subtask(subtask: str) -> StreamingResponse:
    """
    API endpoint to run a subtask.

    :param subtask: The subtask to run.
    :return: The result of running the subtask.
    """
    return StreamingResponse(manager.run_subtask(subtask))


@app.get("/undo_last_subtask")
def undo_last_subtask() -> str:
    """
    API endpoint to undo the last completed subtask.

    :return: The result of the undo operation.
    """
    return manager.undo_last_subtask()

# confirm run subtasks


@app.post("/confirm_run_subtasks")
async def confirm_run_subtasks(subtasks: List[str]) -> StreamingResponse:
    """
    API endpoint to confirm and run the generated subtasks.

    :param subtasks: The list of subtasks to run.
    :return: The list of responses from running the subtasks.
    """
    return StreamingResponse(manager.confirm_run_subtasks(subtasks))


@app.get("/shutdown")
def shutdown() -> str:
    """
    API endpoint to shutdown all external repo agents.

    :return: "shutdown" after shutting down all agents.
    """
    manager.shutdown()
    os.kill(os.getpid(), signal.SIGTERM)
    return "shutdown"


def main() -> None:
    """
    Main function to run the application.
    """
    parser = argparse.ArgumentParser(
        description="Run the Aider agent manager.")
    parser.add_argument(
        '--port',
        type=int,
        help='Port of the agent',
        default=10000)
    args = parser.parse_args()

    import uvicorn  # Import Uvicorn for running the FastAPI app
    uvicorn.run(app, host="0.0.0.0", port=args.port)


# Run the application with Uvicorn
if __name__ == "__main__":
    main()
