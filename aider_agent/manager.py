from fastapi import FastAPI

from aider.coders import Coder
from aider.models import Model

import argparse

import subprocess
import requests
import logging

app = FastAPI()

START_PORT = 0

class Manager():
    def __init__(self) -> None:
        self.agents = dict()
        self.logger = logging.getLogger("manager")

    def create(self, agent_name, repo_dir="."):
        if agent_name in self.agents:
            return "error: name already exists"
        
        global START_PORT
        while True:
            process = subprocess.Popen(f"cd {repo_dir} && aider_agent_run --port {START_PORT}", shell=True, stdout=subprocess.PIPE)
            self.logger.info(f"Attempt to start agent on port {START_PORT}")
            START_PORT += 1
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                if process.returncode is None:
                    self.logger.info(f"Agent on port {START_PORT} still running, assuming successful")
                    break
                self.logger.info(f"Agent on port {START_PORT} terminated, continue trying...")
            # process terminated
            self.logger.info(f"Agent on port {START_PORT} terminated, continue trying...")

        self.agents[agent_name] = (START_PORT - 1, process)
        return "success"

    def send_msg(self, agent_name, msg):
        response = requests.post(
            f"http://0.0.0.0:{self.agents[agent_name][0]}/msg",
            params={"msg": msg},
        )
        return response.text

    def ask(self, agent_name, msg):
        response = requests.post(
            f"http://0.0.0.0:{self.agents[agent_name][0]}/ask",
            params={"msg": msg},
        )
        return response.text

    def get_agents(self):
        return str(self.agents)

manager = Manager()

# create agent                                                                                                                                                             
@app.post("/create")                                                                                                                                                                                                                                 
def create(agent_name: str):                                                                                                                                                                                                                  
    result = manager.create(agent_name)                                                                                                                                                                                             
    return {"result": result}       

# send a message to aider                                                                                                                                                                           
@app.post("/msg")                                                                                                                                                                                                                                 
def send_msg(agent_name, msg: str):                                                                                                                                                                                                                  
    result = manager.send_msg(agent_name, msg)                                                                                                                                                                                             
    return {"result": result}                

# ask aider                                                                                                                                                                           
@app.post("/ask")                                                                                                                                                                                                                                 
def ask(agent_name, msg: str):                                                                                                                                                                                                                  
    result = manager.ask(agent_name, msg)                                                                                                                                                                                             
    return {"result": result}           

# get agents                                                                                                                                                                       
@app.get("/get_agents")                                                                                                                                                                                                                                 
def get_agents():                                                                                                                                                                                                             
    return {"result": manager.get_agents()}                                                                                                                                                                                                       

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, help='port of agent', default="8080")
    args = parser.parse_args()

    global START_PORT
    START_PORT = args.port + 1

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=args.port)

# Run the application with Uvicorn                                                                                                                                                                                                                  
if __name__ == "__main__":
    main()