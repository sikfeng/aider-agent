from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from aider.coders import Coder
from aider.models import Model
from aider.io import InputOutput

import argparse
from typing import AsyncGenerator

import litellm

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

    def get_repo_map(self) -> str:
        # Hack to remove the repomap prefix
        _tmp_prefix = self.coder.repo_map.repo_content_prefix
        self.coder.repo_map.repo_content_prefix = None
        repo_map = self.coder.get_repo_map()
        self.coder.repo_map.repo_content_prefix = _tmp_prefix
        return repo_map

    def reset(self) -> str:
        return self.run("/reset")


class ExternalRepoAgent(BaseRepoAgent):
    """A class to manage the ExternalRepoAgent."""

    def __init__(
            self,
            llm_name: str = "azure/gpt-4o",
            map_tokens: int = 8092) -> None:
        """Initialize the ExternalRepoAgent.

        :param llm_name: The name of the model to use.
        :param map_tokens: Maximum number of tokens for the repo map.
        """
        super().__init__(model_name=llm_name, map_tokens=map_tokens)


class MainRepoAgent(BaseRepoAgent):
    """A class to manage the Main Repo agent."""

    def __init__(
            self,
            model_name: str = "azure/gpt-4o",
            map_tokens: int = 1024) -> None:
        """Initialize the MainRepoAgent.

        :param model_name: The name of the model to use.
        :param map_tokens: Maximum number of tokens for the repo map.
        """
        super().__init__(model_name=model_name)


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
        llm_name=args.model_name,
        map_tokens=args.map_tokens)

    import uvicorn  # Import here to avoid unnecessary dependency if not running as main
    uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
