from fastapi import FastAPI

from aider.coders import Coder
from aider.models import Model
from aider.io import InputOutput

import argparse

import litellm

litellm.suppress_debug_info = True
litellm.set_verbose = False
litellm.drop_params = True


app = FastAPI()

class Agent():
    """
    A class to manage the Aider agent.
    """
    def __init__(self, llm_name="azure/gpt-4o") -> None:
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

    def run(self, msg):
        """
        Run the agent with the given message.

        :param msg: The message to process.
        :return: The result of processing the message.
        """
        self.coder = Coder.create(
            from_coder=self.coder,
            edit_format=None,
            summarize_from_coder=False,
            io=self.io,
        )
        result = self.coder.run(msg)   
        return str(result)

    def ask(self, msg):
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
def send_msg(msg: str):
    """
    API endpoint to send a message to the agent.

    :param msg: The message to send.
    :return: The result of the message.
    """
    result = agent.run(msg)                                                                                                                                                                                             
    return {"result": result}                

# ask aider                                                                                                                                                                           
@app.post("/ask")                                                                                                                                                                                                                                 
def ask(msg: str):
    """
    API endpoint to ask a question to the agent.

    :param msg: The question to ask.
    :return: The result of the question.
    """
    result = agent.ask(msg)                                                                                                                                                                                             
    return {"result": result}

@app.post("/ping")                                                                                                                                                                                                                                 
def ping():
    """
    API endpoint to ping the agent.

    :return: "pong" if the agent is alive.
    """
    result = "pong"
    return {"result": result}     

def main():
    """
    Main function to run the agent application.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, help='port of agent', default="8080")
    parser.add_argument('--model-name', type=str, help='name of model to use', default="azure/gpt-4o")
    args = parser.parse_args()

    import uvicorn                                                                  
    uvicorn.run(app, host="0.0.0.0", port=args.port)    

                                                                                                                                                                                                                 
if __name__ == "__main__":                                                                                                                                                                                                                          
    main()
