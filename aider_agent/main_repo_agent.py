from aider.coders import Coder
from aider.models import Model
from aider.io import InputOutput

# TODO: error handling

class MainRepoAgent():
    """
    A class to manage the Aider agent.
    """
    coder = None

    def __init__(
            self,
            model_name: str = "azure/gpt-4o") -> None:
        """
        Initialize the AiderAgent.

        :param model_name: The name of the model to use.
        :param repo_dir: The directory of the repository.
        """

        self.model_name = model_name
        self.model = Model(self.model_name)

        self.io = InputOutput(
            pretty=False,
            yes=True,
        )
        self.coder = Coder.create(
            main_model=self.model,
            io=self.io,
            suggest_shell_commands=False
        )
        return

    def run(self, msg: str) -> str:
        """
        Run the agent with the given message.

        :param msg: The message to process.
        :return: The result of processing the message.
        """
        try:
            result = self.coder.run("/code " + msg)
            return str(result)
        except BaseException: # TODO: use narrower exception
            return "error: failed"

    async def run_stream(self, msg: str):
        """
        Run the agent with the given message and stream the response.

        :param msg: The message to process.
        :return: An async generator yielding parts of the response.
        """
        for partial_response in self.coder.run_stream("/code " + msg):
            yield partial_response
        # return self.coder.run_stream(msg)

    def ask(self, msg: str):
        """
        Ask a question to the Aider agent.

        :param msg: The question to ask.
        :return: The response from the agent.
        """
        return self.run_stream("/ask " + msg)

    def run_cmd(self, cmd: str) -> str:
        """
        Run a command using the Aider agent.

        :param cmd: The command to run.
        :return: The response from the agent.
        """
        return self.run("/run " + cmd)

    def get_repo_map(self) -> str:
        # Hack to remove the repomap prefix
        _tmp_prefix = self.coder.repo_map.repo_content_prefix
        self.coder.repo_map.repo_content_prefix = None
        repo_map = self.coder.get_repo_map()
        self.coder.repo_map.repo_content_prefix = _tmp_prefix
        return repo_map
    
    def reset(self) -> str:
        return self.run("/reset")
