import asyncio
from pathlib import Path
import re
from typing import AsyncGenerator, Optional, List, TYPE_CHECKING

from raider_backend.repo_agents.base_repo_agent import BaseRepoAgent
from raider_backend import utils
from raider_backend.prompts import MainRepoAgentPrompts

if TYPE_CHECKING:
    from raider_backend.agent_manager import AgentManager

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
        await asyncio.gather(*(self.agent_manager.external_repo_agent_handler.find_relevant_code(agent_id=repo_dir, task=subtask)
                               for repo_dir
                               in self.agent_manager.external_repo_agent_handler.agents.keys()))

        # TODO: I notice that the code snippets are always not found
        # seems to be because external repo handler saves the files to a different name
        for repo_path in self.agent_manager.external_repo_agent_handler.agents.keys():
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

        # TODO: move to prompts.py
        # TODO: consider using taskgen to do this
        message = f"""
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
                yield {"result": partial_response}

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
                    yield {"info": {"suggested_cmd": command.strip()}}

            if self.coder.reflected_message is None:
                break

            message = self.coder.reflected_message

        self.commit()
    
    async def generate_commands(self, subtask: str) -> AsyncGenerator[str, None]:
        system_prompt = MainRepoAgentPrompts.SYSTEM_PROMPT_GENERATE_SHELL_CMD.format(shell = self.agent_manager.shell, os=self.agent_manager.os_name)
        user_prompt = MainRepoAgentPrompts.SYSTEM_PROMPT_GENERATE_SHELL_CMD.format(subtask=subtask)
        response = utils.llm(self.model_name)(
            system_prompt=system_prompt,
            user_prompt=user_prompt
        )
        yield {"result": {"suggested_cmd": response}}