from fastapi import FastAPI

from aider.coders import Coder
from aider.models import Model

import argparse

app = FastAPI()

class Agent():
    def __init__(self) -> None:
        self.model = Model("azure/gpt-4o")
        self.coder = Coder.create(main_model=self.model)                                                   

    def run(self, msg):
        result = self.coder.run(msg)   
        return str(result)

    def ask(self, msg):
        self.coder = Coder.create(
            from_coder=self.coder,
            edit_format="ask",
            summarize_from_coder=False,
        )
        result = self.run(msg) 
        return str(result)

agent = Agent()

# send a message to aider                                                                                                                                                                           
@app.post("/msg")                                                                                                                                                                                                                                 
def send_msg(msg: str):                                                                                                                                                                                                                  
    result = agent.run(msg)                                                                                                                                                                                             
    return {"result": result}                

# ask aider                                                                                                                                                                           
@app.post("/ask")                                                                                                                                                                                                                                 
def ask(msg: str):                                                                                                                                                                                                                  
    result = agent.ask(msg)                                                                                                                                                                                             
    return {"result": result}

@app.post("/ping")                                                                                                                                                                                                                                 
def ping():                                                                                                                                                                                                                  
    result = "pong"
    return {"result": result}     

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, help='port of agent', default="8080")
    args = parser.parse_args()

    import uvicorn                                                                  
    uvicorn.run(app, host="0.0.0.0", port=args.port)    

                                                                                                                                                                                                                 
if __name__ == "__main__":                                                                                                                                                                                                                          
    main()