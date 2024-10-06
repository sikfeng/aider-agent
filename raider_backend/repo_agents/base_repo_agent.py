import logging
from pathlib import Path
from typing import AsyncGenerator

from aider.coders import Coder
from aider.models import Model
from aider.io import InputOutput

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
        self.logger = logging.getLogger(self.__class__.__name__)

        current_path = Path(".").resolve()
        try:
            from git import Repo
            repo = Repo(current_path, search_parent_directories=True)
            self.logger.debug("Git repo already initialized.")
        except:
            repo = Repo.init(current_path)
            self.logger.info("Git repo initialized.")
            repo.index.add("*")
            self.logger.info("Added all files to tracking.")

        self.io = InputOutput(
            pretty=False,
            yes=True,
        )
        self.coder = Coder.create(
            main_model=self.model,
            io=self.io,
            map_tokens=map_tokens,
            suggest_shell_commands=False,
            chat_language="English",
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

    def run_stream(self, msg: str):
        """Run the agent with the given message and stream the response.

        :param msg: The message to process.
        :return: An async generator yielding parts of the response.
        """
        self.coder = Coder.create(
            io=self.coder.io,
            from_coder=self.coder,
            edit_format="architect",
            summarize_from_coder=False,
        )
        for partial_response in self.coder.run_stream(msg):
            yield partial_response

    def ask(self, msg: str):
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
        for partial_response in self.coder.run_stream(msg):
            yield partial_response

    def reset(self) -> None:
        """Reset the agent to its initial state.

        This method resets the internal state of the agent, clearing any
        accumulated context or data. It is useful for starting fresh without
        any prior context influencing the agent's behavior.
        """
        # For some reason cmd_reset accepts a param `args` that is
        # unused, with no default value either...
        self.coder.commands.cmd_reset(None)

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