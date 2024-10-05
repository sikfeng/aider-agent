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

    async def run_subtask(self, session_id: str, subtask: str) -> AsyncGenerator[str, None]:
        """
        Run a subtask using the main Aider agent.

        :param subtask: The subtask to run.
        :return: An async generator yielding parts of the response.
        """
        self.agent_manager.main_repo_agent.reset()
        self.logger.info("Reset MainRepoAgent coder.")

        self.logger.info("Starting to run %s.", subtask)
        self.logger.info("Querying ExternalRepoAgentHandlers.")
        for repo_dir in self.agent_manager.external_repo_agent_handler.agents.keys():
            if not self.agent_manager.external_repo_agent_handler.is_agent_disabled(repo_dir):
                await self.agent_manager.external_repo_agent_handler.find_relevant_code(agent_id=repo_dir, task=subtask, session_id=session_id)
                self.logger.info("Finished searching %s", repo_dir)
                yield {"info": f"Finished searching {repo_dir}"}
            else:
                self.logger.info("Skipping disabled repo %s", repo_dir)
                yield {"info": f"Skipped disabled repo {repo_dir}"}

        for agent_id in self.agent_manager.external_repo_agent_handler.agents.keys():
            if not self.agent_manager.external_repo_agent_handler.is_agent_disabled(agent_id):
                code_snippet_filename = f"code_snippets_{agent_id.replace('/', '').replace('.', '')}.txt"
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

        # TODO: move prompt to prompts.py
        # TODO: consider using taskgen to do this
        # but runtime and llm calls would increase

        # TODO: retrieve files to add to chat
        #repo_map = self.get_repo_map()
        message = f"""
The following task is to be completed:
{subtask}

From the repository, please provide me with the a list of files you will need to edit. Provide their full paths, one per line. Do not include any preamble.

Output Format:
---------------

<file path 1>

<file path 2>

...

<file path N>
"""
        response = ""
        for partial_response in self.ask(message):
            response += partial_response

        for filepath in response.split("\n"):
            filepath = filepath.strip()
            if not filepath:
                continue
            try:
                if Path(filepath).exists():
                    self.coder.commands.cmd_add(filepath)
                    self.logger.info("Added %s.", filepath)
                else:
                    self.logger.warning("File %s does not exist, skipping.", filepath)
            except OSError:
                self.logger.warning("Filepath %s is too long, skipping.", filepath)

        self.logger.info("Files added: %s", str(self.coder.abs_fnames))
        self.coder.commands.cmd_clear(None)
        self.logger.info("Cleared chat history from MainRepoAgent coder.")

        search_replace_rules = """
*SEARCH/REPLACE block* Rules:

Every *SEARCH/REPLACE block* must use this format:
1. The *FULL* file path alone on a line, verbatim. No bold asterisks, no quotes around it, no escaping of characters, etc.
2. The opening fence and code language, eg: ```python
3. The start of search block: <<<<<<< SEARCH
4. A contiguous chunk of lines to search for in the existing source code
5. The dividing line: =======
6. The lines to replace into the source code
7. The end of the replace block: >>>>>>> REPLACE
8. The closing fence: ```

Use the *FULL* file path, as shown to you by the user.

Every *SEARCH* section must *EXACTLY MATCH* the existing file content, character for character, including all comments, docstrings, etc.
If the file contains code or other data wrapped/escaped in json/xml/quotes or other containers, you need to propose edits to the literal contents of the file, including the container markup.

*SEARCH/REPLACE* blocks will replace *all* matching occurrences.
Include enough lines to make the SEARCH blocks uniquely match the lines to change.

Keep *SEARCH/REPLACE* blocks concise.
Break large *SEARCH/REPLACE* blocks into a series of smaller blocks that each change a small portion of the file.
Include just the changing lines, and a few surrounding lines if needed for uniqueness.
Do not include long runs of unchanging lines in *SEARCH/REPLACE* blocks.

Only create *SEARCH/REPLACE* blocks for files that the user has added to the chat!

To move code within a file, use 2 *SEARCH/REPLACE* blocks: 1 to delete it from its current location, 1 to insert it in the new location.

Pay attention to which filenames the user wants you to edit, especially if they are asking you to create a new file.

If you want to put code in a new file, use a *SEARCH/REPLACE block* with:
- A new file path, including dir name if needed
- An empty `SEARCH` section
- The new file's contents in the `REPLACE` section
"""

        message = f"""
{subtask}

If the files you wish to write to do not exist yet, automatically create them.
If you wish to edit a file that is not already added, add the file to the chat.

REMEMBER TO USE SEARCH/REPLACE BLOCKS TO EDIT FILES!!!

{search_replace_rules}
"""
        response = ""
        for _ in range(self.max_reflections):
            curr_response = ""
            self.logger.debug("Message: %s", message)
            for partial_response in self.run_stream(message):
                curr_response += partial_response
                yield {"result": partial_response}

            response += curr_response

            # Check for shell commands and files to add in the response
            shell_cmds = self._check_for_shell_cmds_in_response(curr_response)
            self.logger.debug("Found shell commands %s", shell_cmds)

            if shell_cmds is not None:
                for command in shell_cmds:
                    yield {"info": {"suggested_cmd": command.strip()}}

            if self.coder.reflected_message is None:
                break

            message = self.coder.reflected_message

        self.logger.info("Response: %s", response)

        self.commit()

    @staticmethod
    def _check_for_shell_cmds_in_response(aider_response: str) -> Optional[List[str]]:
        """
        Check if there are shell commands in the Aider agent
        response.

        :param aider_response: The response from the
            Aider agent.
        :return: The shell commands if found, otherwise None.
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
    
    async def generate_commands(self, subtask: str) -> AsyncGenerator[str, None]:
        system_prompt = MainRepoAgentPrompts.SYSTEM_PROMPT_GENERATE_SHELL_CMD.format(shell = self.agent_manager.shell, os=self.agent_manager.os_name)
        user_prompt = MainRepoAgentPrompts.USER_PROMPT_GENERATE_SHELL_CMD.format(subtask=subtask)
        response = utils.llm(self.model_name)(
            system_prompt=system_prompt,
            user_prompt=user_prompt
        )
        yield {"result": {"suggested_cmd": response}}
