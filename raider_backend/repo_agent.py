"""
This module defines classes and functions to manage repository agents that interact with the Aider system.
It provides a FastAPI-based web service to handle various operations such as running code, asking questions,
and retrieving repository maps.
"""
from raider_backend.agent_manager import AgentManager
import argparse
import asyncio
import logging
from pathlib import Path
import re
from typing import AsyncGenerator, Optional, List

from aider.coders import Coder
from aider.models import Model
from aider.io import InputOutput
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import litellm
import uvicorn

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from raider_backend.agent_manager import AgentManager

# Suppress debug information from litellm
litellm.suppress_debug_info = True
litellm.set_verbose = False
litellm.drop_params = True

app = FastAPI()


class BaseRepoAgent:
    """A base class to manage common functionalities for RepoAgents that call Aider."""

    def __init__(
            self,
            model_name: str = "azure/gpt-4o",
            map_tokens: int = 8092) -> None:
        """Initialize the BaseRepoAgent.

        :param model_name: The name of the model to use.
        :param map_tokens: Maximum number of tokens for the repo map.
        """
        self.model_name = model_name
        self.model = Model(model_name)
        self.map_tokens = map_tokens

        self.io = InputOutput(
            pretty=False,
            yes=True,
        )
        self.coder = Coder.create(
            main_model=self.model,
            io=self.io,
            map_tokens=map_tokens,
            suggest_shell_commands=False,
        )

    def run(self, msg: str) -> str:
        """Run the agent with the given message.

        :param msg: The message to process.
        :return: The result of processing the message.
        """
        try:
            self.coder = Coder.create(
                io=self.coder.io,
                from_coder=self.coder,
                edit_format="code",
                summarize_from_coder=False,
            )
            result = self.coder.run(msg)
            return str(result)
        except Exception as e:
            return f"error: failed due to {e}"

    async def run_stream(self, msg: str) -> AsyncGenerator[str, None]:
        """Run the agent with the given message and stream the response.

        :param msg: The message to process.
        :return: An async generator yielding parts of the response.
        """
        self.coder = Coder.create(
            io=self.coder.io,
            from_coder=self.coder,
            edit_format="code",
            summarize_from_coder=False,
        )
        for partial_response in self.coder.run_stream(msg):
            yield partial_response

    def ask(self, msg: str) -> AsyncGenerator[str, None]:
        """Ask a question to the agent.

        :param msg: The question to ask.
        :return: An async generator yielding parts of the response.
        """
        self.coder = Coder.create(
            io=self.coder.io,
            from_coder=self.coder,
            edit_format="ask",
            summarize_from_coder=False,
        )
        return self.coder.run_stream(msg)

    def reset(self) -> None:
        """Reset the agent to its initial state.

        This method resets the internal state of the agent, clearing any
        accumulated context or data. It is useful for starting fresh without
        any prior context influencing the agent's behavior.
        """
        self.coder.commands.cmd_reset()

    def undo(self) -> None:
        """
        Undo the last commit performed by the agent.

        This method reverts the last commit made by the agent,
        effectively undoing the most recent operation. It is useful for
        correcting mistakes or reverting to a previous state.

        Note: Aider does not programmatically return any result
        indicating whether the undo operation was successful, hence we
        are also unable to return anything useful.
        """
        # For some reason cmd_undo accepts a param `args` that is
        # unused, with no default value either...
        self.coder.commands.cmd_undo(None)

    def commit(self) -> None:
        """
        Commit the current changes made by the agent.

        This method performs a commit operation, saving the current state of the
        repository. It is useful for persisting changes made by the agent, ensuring
        that the modifications are recorded in the version control system.

        Note: Aider does not programmatically return any result indicating whether
        the commit operation was successful, hence we are also unable to return
        anything useful.
        """
        self.coder.commands.cmd_commit()

    def _get_repo_map(self) -> str:
        """Retrieve the repository map without the content prefix..

        This method retrieves the repository map, which is a representation
        of the repository's structure and content. The map is used to
        understand the layout and components of the repository, aiding in
        various tasks such as code navigation and analysis.

        :return: The repository map as a string.
        """
        # if not self.coder.repo_map:
        #    return None

        # Hack to remove the repomap prefix
        _tmp_prefix = self.coder.repo_map.repo_content_prefix
        self.coder.repo_map.repo_content_prefix = None
        repo_map = self.coder.get_repo_map()
        self.coder.repo_map.repo_content_prefix = _tmp_prefix
        return repo_map

    def get_repo_map(self) -> str:
        """
        Retrieve the repository map.

        This method is intended to be implemented by subclasses of
        `BaseRepoAgent` to provide a repository map, which is a
        representation of the repository's structure and content. The
        implementation can vary based on the type of repository:

        - For external repositories, which are not expected to be
            modified, the repository map can be stored once and
            retrieved directly without querying Aider repeatedly.
        - For the main repository, which is expected to change
            frequently, this method should query Aider each time to get
            the most up-to-date repository map.

        :return: The repository map as a string.
        """
        raise NotImplementedError


class ExternalRepoAgent(BaseRepoAgent):
    """A class to manage the ExternalRepoAgent."""

    def __init__(
            self,
            model_name: str = "azure/gpt-4o",
            map_tokens: int = 8092) -> None:
        """Initialize the ExternalRepoAgent.

        :param modemodelame: The name of the model to use.
        :param map_tokens: Maximum number of tokens for the repo map.
        """
        super().__init__(model_name=model_name, map_tokens=map_tokens)

        self.repo_map = self._get_repo_map()

    def get_repo_map(self) -> str:
        # Expecting that external repo will not be modified
        # Hence we simply store the repo_map and just retrieve it.
        return self.repo_map


class MainRepoAgent(BaseRepoAgent):
    """A class to manage the MainRepoAgent."""

    def __init__(
            self,
            model_name: str = "azure/gpt-4o",  # Get strong and weak model
            map_tokens: int = 1024,
            max_reflections: int = 5,
            agent_manager: 'AgentManager' = None) -> None:
        """Initialize the MainRepoAgent.

        :param model_name: The name of the model to use.
        :param map_tokens: Maximum number of tokens for the repo map.
        :param agent_manager: The AgentManager instance.
        """
        super().__init__(model_name=model_name, map_tokens=map_tokens)
        self.agent_manager = agent_manager
        self.max_reflections = max_reflections
        self.logger = logging.getLogger("MainRepoAgent")

    def get_repo_map(self) -> str:
        # Expected that the main repo will keep updating
        repo_map = self._get_repo_map()
        return repo_map

    async def run_subtask(self, subtask: str) -> AsyncGenerator[str, None]:
        """
        Run a subtask using the main Aider agent.

        :param subtask: The subtask to run.
        :return: An async generator yielding parts of the response.
        """
        self.logger.info("Starting to run %s.", subtask)
        self.logger.info("Querying ExternalRepoAgentHandlers.")
        await asyncio.gather(*(external_repo_agent.find_relevant_code(subtask)
                               for external_repo_agent
                               in self.agent_manager.external_repo_agent_handlers.values()))

        for repo_path in self.agent_manager.external_repo_agent_handlers:
            code_snippet_filename = f"code_snippets_{repo_path.replace('/', '').replace('.', '')}.txt"
            if not Path(code_snippet_filename).is_file():
                self.logger.warning(
                    "Did not find %s, skipping.", code_snippet_filename)
                continue

            self.logger.info("Found %s.", code_snippet_filename)
            try:
                self.coder.commands.cmd_read_only(
                    code_snippet_filename)
            except BaseException:
                self.logger.warning(
                    "Error adding %s, skipping.", code_snippet_filename)

        # TODO: I dont like to rely on past completed tasks. I plan to remove this in the future
        completed_tasks = ""

        if self.agent_manager.completed_subtasks:
            completed_tasks = "These are the tasks that you have already completed:\n"
            completed_tasks += "\n".join(
                [f"{j+1}: {t}" for j,
                 t in enumerate(self.agent_manager.completed_subtasks)]
            )

        message = ""
        if self.agent_manager.completed_subtasks:
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
            self.logger.debug("Message: %s", message)
            async for partial_response in self.run_stream(message):
                curr_response += partial_response
                yield partial_response

            response += curr_response

            # Check for shell commands and files to add in the response
            def check_for_shell_cmds_in_response(
                    aider_response: str) -> Optional[List[str]]:
                """
                Check if there are shell commands in the Aider agent
                response.

                :param aider_response: The response from the
                    Aider agent.
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
                matches = shell_code_pattern.findall(aider_response)

                if not matches:
                    return None

                return matches

            # Check for shell commands and files to add in the response
            shell_cmds = check_for_shell_cmds_in_response(curr_response)
            self.logger.debug("Found shell commands %s", shell_cmds)

            if shell_cmds is not None:
                for command in shell_cmds:
                    yield f"\n<suggested_cmd>{command}</suggested_cmd>\n"
                    # Optionally, you can execute the command here if needed
                    # cmd_response = self.main_repo_agent.run_cmd(command)
                    # yield f"<cmd_response>{cmd_response}</cmd_response>"

            # Use the new function to find files to add

            if self.coder.reflected_message is None:
                break

            message = self.coder.reflected_message

        self.commit()
        self.agent_manager.completed_subtasks.append(subtask)


# Global agent instance
agent: ExternalRepoAgent = None

# TODO: move the routes into ExternalRepoAgent


@app.post("/run")
def run(msg: str) -> dict:
    """API endpoint to send a message to the agent.

    :param msg: The message to send.
    :return: The result of the message.
    """
    result = agent.run(msg)
    return {"result": result}


@app.post("/run_stream")
async def run_stream(msg: str) -> StreamingResponse:
    """API endpoint to send a message to the agent and get a streaming response.

    :param msg: The message to send.
    :return: A StreamingResponse with the result of the message.
    """
    return StreamingResponse(agent.run_stream(msg))


@app.post("/ask")
async def ask(msg: str) -> StreamingResponse:
    """API endpoint to ask a question to the agent.

    :param msg: The question to ask.
    :return: A StreamingResponse with the result of the question.
    """
    return StreamingResponse(agent.ask(msg))


@app.get("/get_repo_map")
def get_repo_map() -> str:
    """
    API endpoint to get the repository map.

    :return: The repository map as a string.
    """
    result = agent.get_repo_map()
    return result


@app.get("/ping")
def ping() -> str:
    """
    API endpoint to ping the agent.

    :return: "pong" if the agent is alive.
    """
    result = "pong"
    return result


def main() -> None:
    """
    Main function to run the agent application.
    """
    parser = argparse.ArgumentParser(
        description="Start an aider instance.")
    parser.add_argument(
        '--port',
        type=int,
        help='Port for http requests',
        default=8080)
    parser.add_argument(
        '--model-name',
        type=str,
        help='Name of the model to use',
        default="azure/gpt-4o")
    parser.add_argument(
        '--map-tokens',
        type=int,
        help='Maximum number of tokens for repo map',
        default=8092)
    args = parser.parse_args()

    global agent
    agent = ExternalRepoAgent(
        model_name=args.model_name,
        map_tokens=args.map_tokens)

    uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()

# Import AgentManager at the end to avoid circular imports
