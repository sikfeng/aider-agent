"""
This module defines the `AgentManager` class, which is responsible for
managing the overall process and agents in the system. The
`AgentManager` class initializes and coordinates various agents,
including the main repository agent, external repository agents, and
the planner agent. It provides methods to generate and run subtasks,
initialize agents, and manage the state of the system.
"""
import asyncio
import logging
import os
from pathlib import Path
import platform
import re
from typing import AsyncGenerator, List, Dict, Optional

from distro import name as distro_name
import litellm

from . import utils
from .external_repo_agent_handler import ExternalRepoAgentHandler, \
    InitExternalRepoAgentError
from .planner_agent import PlannerAgent
from .repo_agent import MainRepoAgent

litellm.drop_params = True
litellm.suppress_debug_info = True
litellm.set_verbose = False


class AgentManager:
    """
    A class to manage the overall process and agents.
    """

    def __init__(self, model_name: str = "azure/gpt-4o",
                 max_reflections: int = 5,
                 max_concurrent_queries: int = 1) -> None:
        """
        Initialize the AgentManager.
        """
        self.planner_agent: Optional[PlannerAgent] = None
        self.main_repo_agent: Optional[MainRepoAgent] = None
        self.external_repo_agent_handlers: Dict[str,
                                                ExternalRepoAgentHandler] = {}
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
                ("Attempt to initialize ExternalRepoAgent on non-existent "
                 "directory %s, skipping."),
                repo_dir)
            return False
        if repo_dir == utils.get_absolute_path("."):
            self.logger.warning(
                ("Attempt to initialize ExternalRepoAgent on main repo, "
                 "skipping."))
            return False
        if repo_dir in self.external_repo_agent_handlers:
            self.logger.warning(
                ("Attempt to initialize a new ExternalRepoAgent on already "
                 "initialized repo, skipping."))
            return False

        try:
            agent = ExternalRepoAgentHandler(
                model_name=model_name, repo_dir=repo_dir)
            self.external_repo_agent_handlers[repo_dir] = agent
            self.logger.info(
                "Successfully initialized an ExternalRepoAgent on %s.",
                repo_dir)
            return True
        except InitExternalRepoAgentError:
            self.logger.warning(
                "Failed to initialize an ExternalRepoAgent on %s.", repo_dir)
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
        self.logger.info("Generating subtasks for %s.", objective)
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

        # TODO: refactor parts of this method under MainAiderAgent instead

        self.logger.info("Starting to run %s.", subtask)
        self.logger.info("Querying ExternalRepoAgentHandlers.")
        await asyncio.gather(*(external_repo_agent.find_relevant_code(subtask)
                               for external_repo_agent
                               in self.external_repo_agent_handlers.values()))

        for repo_path in self.external_repo_agent_handlers:
            code_snippet_filename = f"code_snippets_{repo_path.replace('/', '').replace('.', '')}.txt"
            if not Path(code_snippet_filename).is_file():
                self.logger.warning(
                    "Did not find %s, skipping.", code_snippet_filename)
                continue

            self.logger.info("Found %s.", code_snippet_filename)
            try:
                self.main_repo_agent.commands.cmd_read_only(
                    code_snippet_filename)
            except BaseException:
                self.logger.warning(
                    "Error adding %s, skipping.", code_snippet_filename)

        completed_tasks = ""

        if self.completed_subtasks:
            completed_tasks = "These are the tasks that you have already completed:\n"
            completed_tasks += "\n".join(
                [f"{j+1}: {t}" for j,
                 t in enumerate(self.completed_subtasks)]
            )

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
            self.logger.debug("Message: %s", message)
            async for partial_response in self.main_repo_agent.run_stream(message):
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

            if self.main_repo_agent.coder.reflected_message is None:
                break

            message = self.main_repo_agent.coder.reflected_message

        self.main_repo_agent.commit()
        self.completed_subtasks.append(subtask)

    def undo(self) -> None:
        """
        Undo the last commit made by Aider.
        """
        self.main_repo_agent.undo()

    async def run_multiple_subtasks(
            self, subtasks: List[str]) -> AsyncGenerator[str, None]:
        """
        Run the subtasks.

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
            "ExternalRepoAgents: %s", self.external_repo_agent_handlers.keys)
        return list(self.external_repo_agent_handlers.keys())

    def shutdown(self) -> str:
        """
        Shutdown all external repo agents.

        :return: "shutdown" after shutting down all agents.
        """
        for repo_dir, external_repo_agent in self.external_repo_agent_handlers.items():
            self.logger.info("Killing ExternalRepoAgent on %s.", repo_dir)
            external_repo_agent.kill()
        return "shutdown"
