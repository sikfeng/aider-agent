from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from aider.coders import Coder
from aider.models import Model
from aider.io import InputOutput

import argparse
from typing import AsyncGenerator

import litellm

litellm.suppress_debug_info = True
litellm.set_verbose = False
litellm.drop_params = True


app = FastAPI()

class Agent:
    """
    A class to manage the Aider agent.
    """
    def __init__(self, llm_name: str = "azure/gpt-4o", map_tokens = 8092) -> None:
        """
        Initialize the Agent.

        :param llm_name: The name of the model to use.
        """
        self.llm_name = llm_name
        self.model = Model(llm_name)
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
        self.repo_map = self.coder.get_repo_map()
        return

    def run_stream(self, msg: str) -> AsyncGenerator[str, None]:
        """
        Run the agent with the given message and stream the response.

        :param msg: The message to process.
        :return: An async generator yielding parts of the response.
        """
        return self.coder.run_stream("/code " + msg)

    def run(self, msg: str) -> str:
        """
        Run the agent with the given message.

        :param msg: The message to process.
        :return: The result of processing the message.
        """
        try:
            result = self.coder.run("/code ", msg)
            return str(result)
        except:
            return "error: failed"

    def ask(self, msg: str) -> str:
        """
        Ask a question to the agent.

        :param msg: The question to ask.
        :return: The result of the question.
        """
        return self.coder.run_stream("/ask " + msg)
    
    def get_repo_map(self) -> str:
        return self.repo_map

agent = None

# send a message to aider
@app.post("/msg")
def send_msg(msg: str) -> dict:
    """
    API endpoint to send a message to the agent.

    :param msg: The message to send.
    :return: The result of the message.
    """
    result = agent.run(msg)
    return {"result": result}

# send a message to aider, but get stream
@app.post("/run_stream")
async def run_stream(msg: str) -> StreamingResponse:
    """
    API endpoint to send a message to the agent and get a streaming response.

    :param msg: The message to send.
    :return: A StreamingResponse with the result of the message.
    """
    return StreamingResponse(agent.run_stream(msg))

# ask aider
@app.post("/ask")
async def ask(msg: str) -> StreamingResponse:
    """
    API endpoint to ask a question to the agent.

    :param msg: The question to ask.
    :return: The result of the question.
    """
    return StreamingResponse(agent.ask(msg))

@app.get("/get_repo_map")
def get_repo_map() -> str:
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
    parser = argparse.ArgumentParser(description="Start an aider instance.")
    parser.add_argument('--port', type=int, help='Port for http requests', default=8080)
    parser.add_argument('--model-name', type=str, help='Name of the model to use', default="azure/gpt-4o")
    parser.add_argument('--map-tokens', type=int, help='Maximum number of tokens for repo map', default=8092)
    args = parser.parse_args()

    global agent
    agent = Agent(llm_name=args.model_name, map_tokens=args.map_tokens)

    import uvicorn  # Import here to avoid unnecessary dependency if not running as main
    uvicorn.run(app, host="0.0.0.0", port=args.port)

if __name__ == "__main__":
    main()
