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
from logging.config import dictConfig
import os
from pathlib import Path
import platform
from typing import AsyncGenerator, List, Dict, Optional, Any
import argparse

from distro import name as distro_name
from fastapi import FastAPI
import uvicorn

from raider_backend import utils
from raider_backend.handlers.external_repo_agent_handler import ExternalRepoAgentHandler, InitExternalRepoAgentError
from raider_backend.planner_agent import PlannerAgent
from raider_backend.repo_agents.main_repo_agent import MainRepoAgent
from raider_backend.logger import LOG_CONFIG


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
        self.external_repo_agent_handler: ExternalRepoAgentHandler = ExternalRepoAgentHandler()
        self.logger = logging.getLogger(self.__class__.__name__)
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

        self.init_planner_agent()
        self.init_main_repo_agent()

    def init_external_repo_agent(
            self,
            repo_dir: str,
            model_name: str = "azure/gpt-4o",
            timeout: int = 10) -> bool:
        """
        Initialize an external repo agent.

        :param repo_dir: The directory of the repository.
        :param model_name: The name of the model to use.
        :param timeout: Timeout for agent initialization.
        :return: True if the agent is initialized, otherwise False.
        """
        repo_dir = utils.get_absolute_path(repo_dir)
        if not Path(repo_dir).is_dir():
            self.logger.warning(
                "Attempt to initialize ExternalRepoAgent on non-existent "
                "directory %s, skipping.", repo_dir)
            return False
        if repo_dir == utils.get_absolute_path("."):
            self.logger.warning(
                "Attempt to initialize ExternalRepoAgent on main repo, "
                "skipping.")
            return False
        
        agent_id = repo_dir
        if agent_id in self.external_repo_agent_handler.agents:
            self.logger.warning(
                "Attempt to initialize a new ExternalRepoAgent on already initialized repo.")
            if self.external_repo_agent_handler.is_agent_disabled(agent_id):
                self.logger.info(
                    "ExternalRepoAgent on %s is disabled. Enabling now.", repo_dir, repo_dir)
                return True
            return False

        try:
            self.external_repo_agent_handler.initialize_agent(
                agent_id=agent_id,
                repo_dir=repo_dir,
                model_name=model_name,
                timeout=timeout
            )
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
            self.main_repo_agent = MainRepoAgent(
                model_name=model_name, agent_manager=self)
            self.logger.info("MainRepoAgent successfully initialized.")
            return True
        except BaseException as e:
            self.logger.error("MainRepoAgent failed to initialize: %s", str(e))
            return False

    def init_planner_agent(self, model_name: str = "bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0") -> bool:
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

    async def ask_repo(self, query: str):
        for partial_response in self.main_repo_agent.ask(query):
            yield {"result": partial_response}

    async def generate_subtasks(self, objective: str):
        """
        Generate a list of subtasks to achieve the given objective.

        :param objective: The main objective.
        :return: A list of subtasks.
        """
        self.logger.info("Generating subtasks for %s.", objective)
        async for partial_response in self.planner_agent.generate_subtasks(objective):
            yield partial_response

    def finetune_subtasks(self, objective: str, instruction: str) -> List[str]:
        """
        Finetune the generated subtasks based on additional instructions.

        :param objective: The main objective.
        :param instruction: Additional instructions for finetuning.
        :return: A list of finetuned subtasks.
        """
        raise NotImplementedError

    async def run_subtask(self, subtask: str, session_id: str) -> AsyncGenerator[str, None]:
        """
        Run a subtask using the main Aider agent.

        :param subtask: The subtask to run.
        :return: An async generator yielding parts of the response.
        """
        async for response in self.main_repo_agent.run_subtask(subtask=subtask, session_id=session_id):
            yield response

    async def generate_commands(self, subtask: str) -> AsyncGenerator[str, None]:
        """
        Generate commands to perform a subtask.

        :param subtask: The subtask to complete.
        :return: An async generator yielding parts of the response.
        """
        async for response in self.main_repo_agent.generate_commands(subtask):
            yield response

    def undo(self) -> None:
        """
        Undo the last commit made by Aider.
        """
        self.main_repo_agent.undo()
        return {"result": "Undo command sent"}

    def get_external_repo_agents(self) -> List[str]:
        """
        Get a list of all initialized external repo agents.

        :return: A list of initialized external repo agents.
        """
        self.logger.debug(
            "ExternalRepoAgents: %s", self.external_repo_agent_handler.agents.keys())
        return list(self.external_repo_agent_handler.agents.keys())

    def shutdown(self) -> str:
        """
        Shutdown all external repo agents.

        :return: "shutdown" after shutting down all agents.
        """
        self.external_repo_agent_handler.kill_all_agents()
        return {"result": "shutdown"}

    def disable_external_repo_agent(self, repo_dir: str) -> None:
        """
        Disable an external repo agent.

        :param repo_dir: The directory of the repository to disable.
        """
        repo_dir = utils.get_absolute_path(repo_dir)
        self.external_repo_agent_handler.disable_agent(repo_dir)
        self.logger.info(f"Disabled external repo agent for {repo_dir}")
        return {"result": "Success"}

    def enable_external_repo_agent(self, repo_dir: str) -> Dict[str, str]:
        """
        Enable a previously disabled external repo agent.

        :param repo_dir: The directory of the repository to enable.
        :return: A dictionary with the result of the operation.
        """
        repo_dir = utils.get_absolute_path(repo_dir)
        self.external_repo_agent_handler.enable_agent(repo_dir)
        self.logger.info(f"Enabled external repo agent for {repo_dir}")
        return {"result": "Success"}

def main():
    # Initialize the connection manager for AgentManager
    from raider_backend.connection_managers.agent_manager_connection_manager import AgentManagerConnectionManager
    conn_manager = AgentManagerConnectionManager()

    # Set up FastAPI application
    app = FastAPI()
    app.add_api_websocket_route(
        "/ws/{session_id}", conn_manager.websocket_endpoint)
    app.add_api_route("/ping", conn_manager.ping)

    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Run AgentManager with FastAPI WebSocket")
    parser.add_argument("--port", type=int, default=8000,
                        help="Port for the FastAPI server")
    parser.add_argument("--main-repo-dir", type=str, required=True,
                        help="Main repository directory")
    parser.add_argument("--model-name", type=str, default="azure/gpt-4o",
                        help="Model name for the AgentManager")
    parser.add_argument(
        '--logfile',
        type=str,
        help='Path to logfile',
        default=utils.get_tmp_file("agent_manager"),
    )

    # Parse command-line arguments
    args = parser.parse_args()

    # Configure logging
    LOG_CONFIG['handlers']['fileHandler']['filename'] = utils.get_absolute_path(args.logfile)

    # Apply logging configuration
    dictConfig(LOG_CONFIG)

    # Set the working directory to the main repository directory
    args.main_repo_dir = utils.get_absolute_path(args.main_repo_dir)
    os.chdir(args.main_repo_dir)

    # Run the FastAPI server
    uvicorn.run(app, host="localhost", port=args.port)


if __name__ == "__main__":
    main()
