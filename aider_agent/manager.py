from fastapi import FastAPI

import argparse

import subprocess
import requests
import logging

import os

import litellm
from litellm import completion

litellm.suppress_debug_info = True
litellm.set_verbose = False
litellm.drop_params = True


from strictjson import *

app = FastAPI()

START_PORT = -1

class AiderAgent():
    repo_dir: str = "."
    port:int = -1
    logger: logging.Logger
    _process = None
    user_access: bool = False

    def __init__(self, model_name="azure/gpt-4o", repo_dir: str="."):

        self.logger = logging.getLogger(f"agent {repo_dir}")
        self.repo_dir = repo_dir

        global START_PORT
        while True:
            process = subprocess.Popen(f"init_aider_agent --port {START_PORT} --model-name {model_name}", cwd=repo_dir, shell=True)
            self.logger.info(f"Attempt to start agent on port {START_PORT} with model {model_name}")
            self.port = START_PORT
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


    def send_msg(self, msg):
        response = requests.post(
            f"http://0.0.0.0:{self.port}/msg",
            params={"msg": msg},
        )
        return response.json()["result"]

    def ask(self, msg):
        response = requests.post(
            f"http://0.0.0.0:{self.port}/ask",
            params={"msg": msg},
        )
        return response.json()["result"]
    
    def check_alive(self):
        poll = self._process.poll()
        if poll == None:
            return "alive"
        else:
            return "dead"


class PlannerAgent():
    def __init__(self, model_name="azure/gpt-4o") -> None:
        self.model_name = model_name
        #self.agent = cf.Agent(name="planner", model=self.model)
        self.logger = logging.getLogger("planner")
        return

    def llm(self, system_prompt: str, user_prompt: str) -> str:
        
        # define your own LLM here
        response = completion(
            model='azure/gpt4o',
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        return response.choices[0].message.content

    def generate_subtasks(self, objective) -> list[str]:
        system_msg = """You're a diligent software engineer AI.

Create a plan consisting of multiple tasks to complete the provided objective.

Each task should be a discrete, actionable step that contributes to the overall objective. Do not waste time on uneccessary or redundant steps.
Don't create needless tasks like "document the findings".

DO NOT attempt to implement functionality that the user did not ask for. Only implement what the user asked.
"""

        res = strict_json(system_prompt = system_msg,
                            user_prompt = objective,
                            output_format = {'Plan': 'Array of subtasks, type: Array[str]'},
                            llm = self.llm)
        print(res)
        return res['Plan']
    
    def finetune_subtasks(self, objective, instruction):
        # TODO
        return []

class Manager():
    def __init__(self) -> None:
        self.planner_agent = None
        self.main_aider_agent = None
        self.aider_agents = dict()
        self.logger = logging.getLogger("manager")
        self.task = None
        return

    def init_aider_agent(self, agent_name, repo_dir="."):
        if agent_name in self.aider_agents:
            return "error: name already exists"
        
        agent = AiderAgent(name=agent_name, repo_dir=repo_dir)

        self.aider_agents[agent_name] = agent
        return "success"
    
    def init_main_aider_agent(self):
        agent = AiderAgent(model_name="azure/gpt-4o", repo_dir=".")

        self.main_aider_agent = agent
        return "success"
    
    def init_planner_agent(self, model_name="azure/gpt-4o"):
        self.planner_agent = PlannerAgent(model_name)
        return "success"

    def generate_subtasks(self, objective: str) -> list[str]:
        self.task = self.planner_agent.generate_subtasks(objective)
        subtasks = self.task
        return subtasks
        
    def finetune_subtasks(self, objective, instruction):
        return "TODO"

    def confirm_run_subtasks(self, subtasks) -> list[str]:
        if self.task is None:
            return ["failed: no task generated yet"]
        
        #if len(self.aider_agents) == 0:
        #    return "failed: no aider agent"

        tasks = subtasks
        
        responses = []
        for i, task in enumerate(tasks):
            completed_tasks = ""

            if i > 0:
                completed_tasks = "These are the tasks that you have already completed:\n"
                completed_tasks += "\n".join([f"{j+1}: {t}" for j, t in enumerate(tasks[:i])])
            
            message = f"""{completed_tasks}

            Based on the above completed tasks, you are to complete the following task:
            {task}

            If the files you wish to write to do not exist yet, automatically create them.
"""
            response = self.main_aider_agent.send_msg(message)
            print(response)
            responses.append(response)
        
        return responses

    def send_msg(self, agent_name, msg):
        agent = self.aider_agents[agent_name]
        response = agent.send_msg(msg)
        return response.text

    def ask(self, agent_name, msg):
        agent = self.aider_agents[agent_name]
        response = agent.ask(msg)
        return response.text

    def get_agents(self):
        return str(self.aider_agents)

manager = Manager()

# create agent                                                                                                                                                             
@app.post("/init_aider_agent")                                                                                                                                                                                                                                 
def init_aider_agent(repo_dir="."):
    result = manager.init_aider_agent(repo_dir)
    return {"result": result}    

#@app.post("/init_planner_agent")                                                                                                                                                                                                                                 
def init_planner_agent(model_name="azure/gpt-4o"):
    result = manager.init_planner_agent(model_name)
    return {"result": result}     

# get agents                                                                                                                                                                       
@app.get("/get_agents")                                                                                                                                                                                                                                 
def get_agents():                                                                                                                                                                                                             
    return {"result": manager.get_agents()}

# generate subtasks
@app.post("/generate_subtasks")                                                                                                                                                                                                                                 
def generate_subtasks(objective) -> list[str]:                                                                                                                                                                                                           
    return manager.generate_subtasks(objective)

# finetune subtasks
@app.post("/finetune_subtasks")
def finetune_subtasks(objective, instruction):
    return manager.finetune_subtasks(objective, instruction)

# confirm run subtasks
@app.post("/confirm_run_subtasks")
def confirm_run_subtasks(subtasks: list[str]) -> list[str]:
    return manager.confirm_run_subtasks(subtasks)


# send a message to aider
#@app.post("/msg")
def send_msg(agent_name, msg: str):
    result = manager.send_msg(agent_name, msg)
    return {"result": result}

# ask aider
#@app.post("/ask")                                                                                                                                                                                                                                 
def ask(agent_name, msg: str):                                                                                                                                                                                                                  
    result = manager.ask(agent_name, msg)                                                                                                                                                                                             
    return {"result": result}      

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, help='port of agent', default="8080")
    args = parser.parse_args()

    global START_PORT
    START_PORT = args.port + 1

    manager.init_planner_agent()
    manager.init_main_aider_agent()

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=args.port)

# Run the application with Uvicorn                                                                                                                                                                                                                  
if __name__ == "__main__":
    main()
