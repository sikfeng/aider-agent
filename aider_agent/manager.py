'''
TODO
------
Decide whether to use http or websockets
Better error handling
Implement subtask finetuning
Move prompts out of the code
Overload coder.fmt_system_prompt() to continue generating shell commands
Draw mermaid diagram showing flow of top level functions from Manager
Set up litellm load balancing, retries, timeouts etc. https://docs.litellm.ai/docs/proxy/reliability
'''
import litellm
from distro import name as distro_name
import platform
import signal
import os
from pathlib import Path
import asyncio
import logging
import argparse
from fastapi.responses import StreamingResponse
from fastapi import FastAPI
from strictjson import *
from typing import AsyncGenerator, List, Dict, Optional

from fastapi import WebSocket, WebSocketDisconnect

import re
from . import utils
from .external_repo_agent_handler import InitExternalRepoAgentError, ExternalRepoAgentHandler
from .planner_agent import PlannerAgent
from .repo_agent import MainRepoAgent
from logging.config import dictConfig
from .logger import LOG_CONFIG


litellm.suppress_debug_info = True
litellm.set_verbose = False
litellm.drop_params = True

app = FastAPI()


class Manager:
    """
    A class to manage the overall process and agents.
    """

    def __init__(self, model_name: str = "azure/gpt-4o",
                 max_reflections: int = 5,
                 max_concurrent_queries: int = 1) -> None:
        """
        Initialize the Manager.
        """
        self.planner_agent: Optional[PlannerAgent] = None
        self.main_repo_agent: Optional[MainRepoAgent] = None
        self.external_repo_agent_handlers: Dict[str,
                                                ExternalRepoAgentHandler] = dict()
        self.logger = logging.getLogger("AgentManager")
        self.model_name = model_name
        self.max_reflections = max_reflections
        self.max_concurrent_queries = max_concurrent_queries

        self.semaphore = asyncio.Semaphore(
            self.max_concurrent_queries)  # Initialize the semaphore

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
            model_name: str = "azure/gpt-4o") -> bool:
        """
        Initialize an Aider agent.

        :param repo_dir: The directory of the repository.
        :param model_name: The name of the model to use.
        :return: True if the agent is initialized, otherwise False.
        """
        repo_dir = utils.get_absolute_path(repo_dir)
        if not Path(repo_dir).is_dir():
            self.logger.warning(
                f"Attempt to initialize ExternalRepoAgent on non-existent directory {repo_dir}, skipping.")
            return False
        if repo_dir == utils.get_absolute_path("."):
            self.logger.warning(
                "Attempt to initialize ExternalRepoAgent on main repo, skipping.")
            return False
        if repo_dir in self.external_repo_agent_handlers:
            self.logger.warning(
                "Attempt to initialize a new ExternalRepoAgent on already initialized repo, skipping.")
            return False

        try:
            agent = ExternalRepoAgentHandler(
                model_name=model_name, repo_dir=repo_dir)
            self.external_repo_agent_handlers[repo_dir] = agent
            self.logger.info(
                f"Successfully initialized an ExternalRepoAgent on {repo_dir}.")
            return True
        except InitExternalRepoAgentError as e:
            self.logger.warning(
                f"Failed to initialize an ExternalRepoAgent on {repo_dir}.")
            return False

    def init_main_repo_agent(self, model_name: str = "azure/gpt-4o") -> bool:
        """
        Initialize the main Aider agent.

        :param model_name: The name of the model to use.
        :return: True if the agent is initialized, otherwise False.
        """
        try:
            self.main_repo_agent = MainRepoAgent(model_name=model_name)
            self.logger.info("MainRepoAgent successfully initialized.")
            return True
        except BaseException as e:
            self.logger.error("MainRepoAgent failed to initialize: %s", str(e))
            return False

    def init_planner_agent(self, model_name: str = "azure/gpt-4o") -> bool:
        """
        Initialize the Planner agent.

        :param model_name: The name of the model to use.
        :return: True if the agent is initialized, otherwise False.
        """
        try:
            self.planner_agent = PlannerAgent(model_name)
            self.logger.info("PlannerAgent successfully initialized.")
            return True
        except BaseException:
            self.logger.error("PlannerAgent failed to initialize.")
            return False

    async def generate_subtasks(self, objective: str) -> List[str]:
        """
        Generate a list of subtasks to achieve the given objective.

        :param objective: The main objective.
        :return: A list of subtasks.
        """
        self.logger.info(f"Generating subtasks for {objective}.")
        return await self.planner_agent.generate_subtasks(objective)

    def finetune_subtasks(self, objective: str, instruction: str) -> List[str]:
        """
        Finetune the generated subtasks based on additional instructions.

        :param objective: The main objective.
        :param instruction: Additional instructions for finetuning.
        :return: A list of finetuned subtasks.
        """
        raise NotImplementedError

    async def run_subtask(self, subtask: str) -> AsyncGenerator[str, None]:
        """
        Run a subtask using the main Aider agent.

        :param subtask: The subtask to run.
        :return: An async generator yielding parts of the response.
        """

        # TODO: something is still running concurrently in here, which gives rate limits
        # even when external repo agents is empty

        self.logger.info(f"Starting to run {subtask}.")
        self.logger.info(f"Querying ExternalRepoAgentHandlers.")
        await asyncio.gather(*(external_repo_agent.find_relevant_code(subtask) for external_repo_agent in self.external_repo_agent_handlers.values()))

        for repo_path in self.external_repo_agent_handlers:
            code_snippet_filename = f"code_snippets_{repo_path.replace('/', '').replace('.','')}.txt"
            self.logger.info(f"Found {code_snippet_filename}.")
            try:
                self.main_repo_agent.run(f"/read-only {code_snippet_filename}")
            except BaseException:  # TODO: use a narrower exception type
                self.logger.warning(
                    f"Did not find {code_snippet_filename}, skipping.")

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
            self.logger.debug(f"Message: {message}")
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
            self.logger.debug(f"Found shell commands {shell_cmds}")

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

    def undo_last_subtask(self) -> bool:
        """
        Undo the last completed subtask.

        :return: True if the undo operation was successful, otherwise False.
        """
        if len(self.completed_subtasks) > 0:
            self.completed_subtasks.pop()
            # TODO: check if result was successful
            result = self.main_repo_agent.run('/undo')
            return True
        else:
            self.logger.warning("No previously completed subtasks.")
            return False

    async def run_multiple_subtasks(
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

    def get_external_repo_agents(self) -> List[str]:
        """
        Get a list of all initialized Aider agents.

        :return: A list of initialized Aider agents.
        """
        self.logger.debug(
            f"ExternalRepoAgents: {self.external_repo_agent_handlers.keys}")
        return list(self.external_repo_agent_handlers.keys())

    def shutdown(self) -> str:
        """
        Shutdown all external repo agents.

        :return: "shutdown" after shutting down all agents.
        """
        for repo_dir, external_repo_agent in self.external_repo_agent_handlers.items():
            self.logger.info(f"Killing ExternalRepoAgent on {repo_dir}.")
            external_repo_agent.kill()
        return "shutdown"


manager = None

logger = logging.getLogger("WebSocketEndpoint")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connection accepted")
    try:
        async def send_keepalive_pings():
            while True:
                await asyncio.sleep(10)  # Adjust the interval as needed
                await websocket.send_json({"ping": "keepalive"})
                logger.debug("Sent keepalive ping")

        keepalive_task = asyncio.create_task(send_keepalive_pings())

        while True:
            data = await websocket.receive_json()
            logger.info(f"Received data: {data}")
            method = data.get("method")
            params = data.get("params", {})

            if method == "init_external_repo_agent":
                repo_dir = params.get("repo_dir")
                result = manager.init_external_repo_agent(repo_dir)
                await websocket.send_json({"result": "Success" if result else "Failure"})
                await websocket.send_json({"result": "</eos_token>"})
                logger.info(f"init_external_repo_agent result: {'Success' if result else 'Failure'}")

            elif method == "get_external_repo_agents":
                agents = str(manager.get_external_repo_agents())
                await websocket.send_json({"result": agents})
                await websocket.send_json({"result": "</eos_token>"})
                logger.info(f"get_external_repo_agents result: {agents}")

            elif method == "generate_subtasks":
                objective = params.get("objective")
                import json
                subtasks = json.dumps(await manager.generate_subtasks(objective))
                await websocket.send_json({"result": subtasks})
                await websocket.send_json({"result": "</eos_token>"})
                logger.info(f"generate_subtasks result: {subtasks}")

            elif method == "finetune_subtasks":
                objective = params.get("objective")
                instruction = params.get("instruction")
                subtasks = manager.finetune_subtasks(objective, instruction)
                await websocket.send_json({"result": subtasks})
                await websocket.send_json({"result": "</eos_token>"})
                logger.info(f"finetune_subtasks result: {subtasks}")

            elif method == "run_subtask":
                subtask = params.get("subtask")
                async for response in manager.run_subtask(subtask):
                    await websocket.send_json({"result": response})
                    logger.info(f"run_subtask response: {response}")
                await websocket.send_json({"result": "</eos_token>"})

            elif method == "run_multiple_subtasks":
                subtasks = params.get("subtasks")
                async for response in manager.run_multiple_subtasks(subtasks):
                    await websocket.send_json({"result": response})
                    logger.info(f"run_multiple_subtasks response: {response}")
                await websocket.send_json({"result": "</eos_token>"})

            elif method == "undo_last_subtask":
                result = manager.undo_last_subtask()
                await websocket.send_json({"result": "Success" if result else "Failure"})
                await websocket.send_json({"result": "</eos_token>"})
                logger.info(f"undo_last_subtask result: {'Success' if result else 'Failure'}")

            elif method == "shutdown":
                manager.shutdown()
                await websocket.send_json({"result": "shutdown"})
                await websocket.send_json({"result": "</eos_token>"})
                logger.info("Shutdown initiated")
                os.kill(os.getpid(), signal.SIGTERM)

    except WebSocketDisconnect:
        logger.warning("Client disconnected")
    finally:
        keepalive_task.cancel()
        logger.info("Keepalive task cancelled")

def main() -> None:
    """
    Main function to run the application.
    """
    parser = argparse.ArgumentParser(
        description="Run the Aider agent manager.")
    parser.add_argument('--port', type=int, help='Port of the agent', default=10000)
    parser.add_argument('--logname', type=str, help='Path to logfile', default="/tmp/manager.log")
    args = parser.parse_args()

    LOG_CONFIG['handlers']['fileHandler']['filename'] = utils.get_absolute_path(args.logname)
    if Path(LOG_CONFIG['handlers']['fileHandler']['filename']).is_file():
        # TODO: ask for user confirmation to overwrite logfile
        # for now I will just overwrite it anyways
        Path(LOG_CONFIG['handlers']['fileHandler']['filename']).unlink()
    dictConfig(LOG_CONFIG)

    global manager
    manager = Manager()
    import uvicorn  # Import Uvicorn for running the FastAPI app
    uvicorn.run(app, host="0.0.0.0", port=args.port)


# Run the application with Uvicorn
if __name__ == "__main__":
    main()
