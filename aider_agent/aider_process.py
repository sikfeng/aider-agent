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
    def __init__(self, llm_name: str = "azure/gpt-4o") -> None:
        """
        Initialize the Agent.

        :param llm_name: The name of the model to use.
        """
        """
        Initialize the Agent.

        :param llm_name: The name of the model to use.
        """
        self.llm_name = "azure/gpt-4o"
        self.model = Model(llm_name)

        self.io = InputOutput(
            pretty=False,
            yes=True,
        )
        self.coder = Coder.create(
            main_model=self.model,
            io=self.io,
        )
        return

    def run_stream(self, msg: str) -> AsyncGenerator[str, None]:
        """
        Run the agent with the given message and stream the response.

        :param msg: The message to process.
        :return: An async generator yielding parts of the response.
        """
        self.coder = Coder.create(
            from_coder=self.coder,
            edit_format=None,
            summarize_from_coder=False,
            io=self.io,
        )
        #async for partial_response in self.coder.run_stream(msg):
        #    yield partial_response
        return self.coder.run_stream(msg)

    def run(self, msg: str) -> str:
        """
        Run the agent with the given message.

        :param msg: The message to process.
        :return: The result of processing the message.
        """
        """
        Run the agent with the given message.

        :param msg: The message to process.
        :return: The result of processing the message.
        """
        try:
            self.coder = Coder.create(
                from_coder=self.coder,
                edit_format=None,
                summarize_from_coder=False,
                io=self.io,
            )
            result = self.coder.run(msg)
            return str(result)
        except:
            return "error: failed"

    def ask(self, msg: str) -> str:
        """
        Ask a question to the agent.

        :param msg: The question to ask.
        :return: The result of the question.
        """
        """
        Ask a question to the agent.

        :param msg: The question to ask.
        :return: The result of the question.
        """
        self.coder = Coder.create(
            from_coder=self.coder,
            edit_format="ask",
            summarize_from_coder=False,
            io=self.io,
        )
        result = self.run(msg)
        return str(result)

agent = Agent()

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
def ask(msg: str) -> str:
    """
    API endpoint to ask a question to the agent.

    :param msg: The question to ask.
    :return: The result of the question.
    """
    result = agent.ask(msg)
    return result

@app.post("/ping")
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
    parser = argparse.ArgumentParser(description="Run the Aider agent application.")
    parser.add_argument('--port', type=int, help='Port of the agent', default=8080)
    parser.add_argument('--model-name', type=str, help='Name of the model to use', default="azure/gpt-4o")
    args = parser.parse_args()

    import uvicorn  # Import here to avoid unnecessary dependency if not running as main
    uvicorn.run(app, host="0.0.0.0", port=args.port)

if __name__ == "__main__":
    main()
