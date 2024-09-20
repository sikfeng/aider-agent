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
from typing import AsyncGenerator, List, Dict, Optional, Any
import argparse

from distro import name as distro_name
import litellm
from fastapi import FastAPI
import uvicorn

from . import utils
from .external_repo_agent_handler import ExternalRepoAgentHandler, InitExternalRepoAgentError
from .planner_agent import PlannerAgent
import raider_backend.repo_agent

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
        self.main_repo_agent: Optional[raider_backend.MainRepoAgent] = None
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
                model_name=model_name, repo_dir=repo_dir, agent_manager=self)
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
            self.main_repo_agent = raider_backend.MainRepoAgent(
                model_name=model_name, agent_manager=self)
            self.logger.info("MainRepoAgent successfully initialized.")
            return True
        except BaseException as e:
            self.logger.error("MainRepoAgent failed to initialize: %s", str(e))
            return False

    def init_planner_agent(self, model_name: str = "bedrock/meta.llama3-1-405b-instruct-v1:0") -> bool:
        """
        Initialize the Planner agent.

        :param model_name: The name of the model to use.
        :return: True if the agent is initialized, otherwise False.
        """
        try:
            self.planner_agent = PlannerAgent(model_name, agent_manager=self)
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
        async for response in self.main_repo_agent.run_subtask(subtask):
            yield response

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
            "ExternalRepoAgents: %s", self.external_repo_agent_handlers.keys())
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

    async def call_agent_function(self, agent_name: str, function_name: str, params: Dict[str, Any]) -> Any:
        """
        Dynamically call a function of a specified agent.

        :param agent_name: The name of the agent to call ('planner', 'main_repo', or 'external_repo_<repo_dir>')
        :param function_name: The name of the function to call
        :param params: A dictionary of parameters to pass to the function
        :return: The result of the function call
        """
        if agent_name == 'planner':
            agent = self.planner_agent
        elif agent_name == 'main_repo':
            agent = self.main_repo_agent
        elif agent_name.startswith('external_repo_'):
            repo_dir = agent_name[len('external_repo_'):]
            agent = self.external_repo_agent_handlers.get(repo_dir)
        else:
            raise ValueError(f"Unknown agent: {agent_name}")

        if agent is None:
            raise ValueError(f"Agent {agent_name} is not initialized")

        if not hasattr(agent, function_name):
            raise AttributeError(
                f"Function {function_name} not found in agent {agent_name}")

        func = getattr(agent, function_name)
        if not callable(func):
            raise AttributeError(
                f"{function_name} is not a callable function in agent {agent_name}")

        return await func(**params)


def main():
    from .connection_manager import AgentManagerConnectionManager
    conn_manager = AgentManagerConnectionManager()

    app = FastAPI()
    app.add_api_websocket_route(
        "/ws/{session_id}", conn_manager.websocket_endpoint)
    app.add_api_route("/ping", conn_manager.ping)

    parser = argparse.ArgumentParser(
        description="Run AgentManager with FastAPI WebSocket")
    parser.add_argument("--port", type=int, default=8000,
                        help="Port for the FastAPI server")
    parser.add_argument("--main-repo-dir", type=str,
                        help="Main repository directory")
    parser.add_argument("--model-name", type=str, default="azure/gpt-4o",
                        help="Model name for the AgentManager")
    args = parser.parse_args()

    args.main_repo_dir = utils.get_absolute_path(args.main_repo_dir)
    os.chdir(args.main_repo_dir)

    uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
