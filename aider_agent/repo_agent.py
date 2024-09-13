"""
This module defines classes and functions to manage repository agents that interact with the Aider system.
It provides a FastAPI-based web service to handle various operations such as running code, asking questions,
and retrieving repository maps.
"""
import argparse
from typing import AsyncGenerator

from aider.coders import Coder
from aider.models import Model
from aider.io import InputOutput
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import litellm
import uvicorn

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
            result = self.coder.run("/code " + msg)
            return str(result)
        except Exception as e:
            return f"error: failed due to {e}"

    async def run_stream(self, msg: str) -> AsyncGenerator[str, None]:
        """Run the agent with the given message and stream the response.

        :param msg: The message to process.
        :return: An async generator yielding parts of the response.
        """
        for partial_response in self.coder.run_stream("/code " + msg):
            yield partial_response

    def ask(self, msg: str) -> AsyncGenerator[str, None]:
        """Ask a question to the agent.

        :param msg: The question to ask.
        :return: An async generator yielding parts of the response.
        """
        return self.coder.run_stream("/ask " + msg)

    def reset(self) -> str:
        """Reset the agent to its initial state.

        This method resets the internal state of the agent, clearing any
        accumulated context or data. It is useful for starting fresh without
        any prior context influencing the agent's behavior.

        :return: The result of the reset operation.
        """
        return self.run("/reset")

    def _get_repo_map(self) -> str:
        # Hack to remove the repomap prefix
        _tmp_prefix = self.coder.repo_map.repo_content_prefix
        self.coder.repo_map.repo_content_prefix = None
        repo_map = self.coder.get_repo_map()
        self.coder.repo_map.repo_content_prefix = _tmp_prefix
        return repo_map

    def get_repo_map(self) -> str:
        """Get the repository map.

        This method retrieves the repository map, which is a representation
        of the repository's structure and content. The map is used to
        understand the layout and components of the repository, aiding in
        various tasks such as code navigation and analysis.

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
            model_name: str = "azure/gpt-4o",
            map_tokens: int = 1024) -> None:
        """Initialize the MainRepoAgent.

        :param model_name: The name of the model to use.
        :param map_tokens: Maximum number of tokens for the repo map.
        """
        super().__init__(model_name=model_name, map_tokens=map_tokens)

    def get_repo_map(self) -> str:
        # Expected that the main repo will keep updating
        repo_map = self._get_repo_map()
        return repo_map


# Global agent instance
agent: ExternalRepoAgent = None


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
