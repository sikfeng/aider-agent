from fastapi import FastAPI

import argparse

import subprocess
import requests
import logging

import os

import controlflow as cf
from langchain_community.chat_models import ChatLiteLLM

import litellm

litellm.suppress_debug_info = True
litellm.set_verbose = False
litellm.drop_params = True

app = FastAPI()

START_PORT = -1

class AiderAgent():
    repo_dir: str = "."
    port:int = -1
    logger: logging.Logger
    _process = None
    user_access: bool = False

    def __init__(self, repo_dir: str=".", **kwargs):
        super().__init__(**kwargs)

        self.logger = logging.getLogger(f"agent {repo_dir}")
        self.repo_dir = repo_dir

        global START_PORT
        while True:
            process = subprocess.Popen(f"init_aider_agent --port {START_PORT}", cwd=repo_dir, shell=True)
            self.logger.info(f"Attempt to start agent on port {START_PORT}")
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
        self.model = ChatLiteLLM(model=model_name)
        self.agent = cf.Agent(name="planner", model=self.model)
        self.logger = logging.getLogger("planner")
        return

    def create_subtasks(self, objective):
        task = cf.Task(
            objective=objective,
            agents=[self.agent]
        )

        task.generate_subtasks()
        return task
    
    def finetune_subtasks(self, objective, instruction):
        # TODO
        task = cf.Task(
            objective=objective,
            instructions=instruction,
            agents=[self.agent]
        )

        task.generate_subtasks()
        return task

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
        agent = AiderAgent(name="main aider agent", repo_dir=".")

        self.main_aider_agent = agent
        return "success"
    
    def init_planner_agent(self, model_name="azure/gpt-4o"):
        self.planner_agent = PlannerAgent(model_name)
        return "success"

    def gen_subtasks(self, objective):
        self.task = self.planner_agent.create_subtasks(objective)
        subtasks = [f'{i+1}: {t.objective}' for i, t in enumerate(self.task.subtasks)]
        return str(subtasks)
        
    def finetune_subtasks(self, objective, instruction):
        self.task = self.planner_agent.finetune_subtasks(objective, instruction)
        subtasks = [f'{i+1}: {t.objective}' for i, t in enumerate(self.task.subtasks)]
        return str(subtasks)

    def confirm_run_subtasks(self) -> list[str]:
        if self.task is None:
            return ["failed: no task"]
        
        #if len(self.aider_agents) == 0:
        #    return "failed: no aider agent"
        
        #print(self.task)
        #return str(self.task)
        #self.task.agent = None
        #self.task.agent = [self.aider_agents[name] for name in self.aider_agents]

        #print(self.task)

        #response = self.task.run(agents=[self.aider_agents[name] for name in self.aider_agents])

        tasks = []
        for i, t in enumerate(self.task.subtasks):
            tasks.append(t.objective)
        
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
            #response = self.main_aider_agent.send_msg("Automatically create new files if they do not exist. " + task)
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
def init_aider_agent(agent_name, repo_dir="."):
    result = manager.init_aider_agent(agent_name, repo_dir)
    return {"result": result}    

#@app.post("/init_planner_agent")                                                                                                                                                                                                                                 
def init_planner_agent(model_name="azure/gpt-4o"):
    result = manager.init_planner_agent(model_name)
    return {"result": result}     

# get agents                                                                                                                                                                       
#@app.get("/get_agents")                                                                                                                                                                                                                                 
def get_agents():                                                                                                                                                                                                             
    return {"result": manager.get_agents()}

# generate subtasks
@app.post("/gen_subtasks")                                                                                                                                                                                                                                 
def gen_subtasks(objective):                                                                                                                                                                                                             
    return {"result": manager.gen_subtasks(objective)}                                                                                                                                                                                                       

# finetune subtasks
#@app.post("/finetune_subtasks")                                                                                                                                                                                                                                 
def finetune_subtasks(objective, instruction):                                                                                                                                                                                                             
    return {"result": manager.finetune_subtasks(objective, instruction)}   

# confirm run subtasks
@app.get("/confirm_run_subtasks")                                                                                                                                                                                                                                 
def confirm_run_subtasks() -> list[str]:
    return manager.confirm_run_subtasks()


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
