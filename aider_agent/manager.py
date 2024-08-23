'''
TODO
------
Prompt tuning
Uee websockets instead
Better error handling
'''

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

import argparse

import subprocess
import requests
import logging

import os
import platform
from distro import name as distro_name

import litellm
from litellm import completion

litellm.suppress_debug_info = True
litellm.set_verbose = False
litellm.drop_params = True

from strictjson import *

from typing import AsyncGenerator

import shutil

app = FastAPI()

START_PORT = -1

class AiderAgent():
    """
    A class to manage the Aider agent.
    """
    repo_dir: str = "."  # Directory of the repository
    port: int = -1  # Port number for the agent
    logger: logging.Logger  # Logger instance for the agent
    _process: subprocess.Popen | None = None  # Subprocess for the agent
    user_access: bool = False  # Flag to indicate user access

    def __init__(self, model_name: str = "azure/gpt-4o", repo_dir: str = ".") -> None:
        """
        Initialize the AiderAgent.

        :param model_name: The name of the model to use.
        :param repo_dir: The directory of the repository.
        """

        self.logger = logging.getLogger(f"agent {repo_dir}")
        self.repo_dir = repo_dir

        global START_PORT
        while True:
            process = subprocess.Popen(f"init_aider_process --port {START_PORT} --model-name {model_name}", cwd=repo_dir, shell=True)
            self.logger.info(f"Attempt to start an aider process on port {START_PORT} with model {model_name}")
            self.port = START_PORT
            START_PORT += 1
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if process.returncode is None:
                    self.logger.info(f"aider process on port {START_PORT} still running, assuming successful")
                    break
                self.logger.info(f"aider process on port {START_PORT} terminated, continue trying...")
            # process terminated
            self.logger.info(f"Agent on port {START_PORT} terminated, continue trying...")


    def run(self, msg: str) -> str:
        """
        Send a message to the Aider agent.

        :param msg: The message to send.
        :return: The response from the agent.
        """
        response = requests.post(
            f"http://0.0.0.0:{self.port}/msg",
            params={"msg": msg},
        )
        return response.json()["result"]

    async def run_stream(self, msg: str, chunk_size: int = 64) -> AsyncGenerator[str, None]:
        """
        Send a message to the Aider agent and stream the response.

        :param msg: The message to send.
        :param chunk_size: The size of each chunk in the stream.
        :return: An async generator yielding parts of the response.
        """
        response = requests.post(
            f"http://0.0.0.0:{self.port}/run_stream",
            params={"msg": msg},
            stream = True
        )
        #return response.json()["result"]
        for partial_response in response.iter_content(chunk_size=chunk_size, decode_unicode=True):
            if isinstance(partial_response, bytes):
                partial_response = partial_response.decode('utf-8')
            yield partial_response

    async def ask(self, msg: str, chunk_size: int = 64) -> AsyncGenerator[str, None]:
        """
        Ask a question to the Aider agent.

        :param msg: The question to ask.
        :return: The response from the agent.
        """
        response = requests.post(
            f"http://0.0.0.0:{self.port}/ask",
            params={"msg": msg},
            stream = True
        )
        for partial_response in response.iter_content(chunk_size=chunk_size, decode_unicode=True):
            if isinstance(partial_response, bytes):
                partial_response = partial_response.decode('utf-8')
            yield partial_response
    
    def run_cmd(self, cmd: str) -> str:
        """
        Run a command using the Aider agent.

        :param cmd: The command to run.
        :return: The response from the agent.
        """
        response = requests.post(
            f"http://0.0.0.0:{self.port}/msg",
            params={"msg": f"/run {cmd}"},
        )
        return response.json()["result"]

    def check_alive(self) -> str:
        """
        Check if the Aider agent process is alive.

        :return: "alive" if the process is running, otherwise "dead".
        """
        poll = self._process.poll()
        if poll == None:
            return "alive"
        else:
            return "dead"
        
    def get_repo_map(self) -> str:
        response = requests.get(
            f"http://0.0.0.0:{self.port}/get_repo_map"
        )
        return response.json()["result"]


class PlannerAgent():
    """
    A class to manage the Planner agent.
    """
    def __init__(self, model_name: str = "azure/gpt-4o") -> None:
        """
        Initialize the PlannerAgent.

        :param model_name: The name of the model to use.
        """
        self.model_name = model_name
        self.logger = logging.getLogger("planner")
        return

    def llm(self, system_prompt: str, user_prompt: str) -> str:
        """
        Generate a response using the LLM.

        :param system_prompt: The system prompt.
        :param user_prompt: The user prompt.
        :return: The response from the LLM.
        """
        """
        Generate a response using the LLM.

        :param system_prompt: The system prompt.
        :param user_prompt: The user prompt.
        :return: The response from the LLM.
        """
        
        # define your own LLM here
        response = completion(
            model='azure/gpt4o',
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        return response.choices[0].message.content

    def generate_subtasks(self, objective: str) -> list[str]:
        """
        Generate a list of subtasks to achieve the given objective.

        :param objective: The main objective.
        :return: A list of subtasks.
        """
        """
        Generate a list of subtasks to achieve the given objective.

        :param objective: The main objective.
        :return: A list of subtasks.
        """
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
        
        return res['Plan']
    
    def finetune_subtasks(self, objective: str, instruction: str) -> list[str]:
        """
        Finetune the generated subtasks based on additional instructions.

        :param objective: The main objective.
        :param instruction: Additional instructions for finetuning.
        :return: A list of finetuned subtasks.
        """
        """
        Finetune the generated subtasks based on additional instructions.

        :param objective: The main objective.
        :param instruction: Additional instructions for finetuning.
        :return: A list of finetuned subtasks.
        """
        # TODO
        return []

class Manager():
    """
    A class to manage the overall process and agents.
    """
    def __init__(self) -> None:
        """
        Initialize the Manager.
        """
        self.planner_agent = None
        self.main_aider_agent = None
        self.aider_agents = dict()
        self.logger = logging.getLogger("manager")
        self.task = None

        def _os_name() -> str:
            current_platform = platform.system()
            if current_platform == "Linux":
                return "Linux/" + distro_name(pretty=True)
            if current_platform == "Windows":
                return "Windows " + platform.release()
            if current_platform == "Darwin":
                return "Darwin/MacOS " + platform.mac_ver()[0]
            return current_platform

        def _shell_name() -> str:
            current_platform = platform.system()
            if current_platform in ("Windows", "nt"):
                is_powershell = len(os.getenv("PSModulePath", "").split(os.pathsep)) >= 3
                return "powershell.exe" if is_powershell else "cmd.exe"
            return os.path.basename(os.getenv("SHELL", "/bin/sh"))

        self.os_name = _os_name()
        self.shell = _shell_name()

        self.completed_subtasks = []

        return

    def init_aider_agent(self, repo_dir: str = ".") -> str:
        """
        Initialize an Aider agent.

        :param repo_dir: The directory of the repository.
        :return: "success" if the agent is initialized, otherwise an error message.
        """
        if repo_dir in self.aider_agents:
            return "error: agent already initialized on this repo dir"
        
        # TODO: convert path to a standardized repr, such as abs path
        
        agent = AiderAgent(model_name="azure/gpt-4o", repo_dir=repo_dir)

        self.aider_agents[repo_dir] = agent
        return "success"
    
    def init_main_aider_agent(self) -> str:
        """
        Initialize the main Aider agent.

        :return: "success" if the agent is initialized.
        """
        agent = AiderAgent(model_name="azure/gpt-4o", repo_dir=".")

        self.main_aider_agent = agent
        return "success"
    
    def init_planner_agent(self, model_name: str = "azure/gpt-4o") -> str:
        """
        Initialize the Planner agent.

        :param model_name: The name of the model to use.
        :return: "success" if the agent is initialized.
        """
        self.planner_agent = PlannerAgent(model_name)
        return "success"

    async def find_relevant_code(self, task):
        results = dict()
        for repo_path, repo_agent in self.aider_agents.items():
            prompt = """
Please look through the repository structure and suggest a list of files that is relevant to the following task.

{task}

Please only provide the full path and return at most 5 files.
The returned files should be separated by new lines ordered by most to least important and wrapped with ```
For example:
```
file1.py
file2.py
```
"""
            async for partial_response in repo_agent.ask(prompt.format(task=task)):
                #print(partial_response, end='')
                yield partial_response
            yield '\n'

            prompt = """
Please look through the added files and suggest code snippets that are most relevant and can be reused for the following task. 

{task}
"""
            async for partial_response in repo_agent.ask(prompt.format(task=task)):
                #print(partial_response, end='')
                yield partial_response
            yield '\n'

            prompt = """For the useful code snippets you had found, add comments to show which file they originated from, and a description of what it does."""
            code_snippet_filename = f"code_snippets_{repo_path.replace('/', '').replace('.','')}.txt"
            response = ""
            async for partial_response in repo_agent.run_stream(prompt.format(code_snippet_filename=code_snippet_filename)):
                response += partial_response
                yield partial_response
            yield '\n'
            
            code_snippet_filename = f"code_snippets_{repo_path.replace('/', '').replace('.','')}.txt"
            with open(code_snippet_filename, 'w') as code_snippet_file:
                code_snippet_file.write(response)

            '''prompt = """Please write these code snippets into a new file `{code_snippet_filename}`."""
            code_snippet_filename = f"code_snippets_{repo_path.replace('/', '').replace('.','')}.txt"
            async for partial_response in repo_agent.run_stream(prompt.format(code_snippet_filename=code_snippet_filename)):
                #print(partial_response, end='')
                yield partial_response
            yield '\n'

            retry_limit = 0
            while not os.path.isfile(code_snippet_filename) and retry_limit > 0:
                retry_limit -= 1
                print(f"error creating {code_snippet_filename}")

                # retry
                async for partial_response in repo_agent.run_stream(f"""You did not write the code snippets to the file {code_snippet_filename}. 
Remember, ALL changes to files must use this *SEARCH/REPLACE block* format.

Please look through the added files and suggest code snippets that are relevant to the following task.

{task}

Write these code snippets into a new file `{code_snippet_filename}`. 
Include comments with their original file names and a description of what the function does."""):
                    #print(partial_response, end='')
                    yield partial_response
                yield '\n'
                '''
                
        return

    def generate_subtasks(self, objective: str) -> list[str]:
        """
        Generate a list of subtasks to achieve the given objective.

        :param objective: The main objective.
        :return: A list of subtasks.
        """
        self.task = self.planner_agent.generate_subtasks(objective)
        subtasks = self.task
        return subtasks
        
    def finetune_subtasks(self, objective: str, instruction: str) -> list[str]:
        return "TODO"

    def llm(self, system_prompt: str, user_prompt: str) -> str:
        """
        Generate a response using the LLM.

        :param system_prompt: The system prompt.
        :param user_prompt: The user prompt.
        :return: The response from the LLM.
        """
        
        # define your own LLM here
        response = completion(
            model='azure/gpt4o',
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        return response.choices[0].message.content

    def check_for_shell_cmds_in_response(self, aider_agent_response: str) -> str | None:
        """
        Check if there are shell commands in the Aider agent response.

        :param aider_agent_response: The response from the Aider agent.
        :return: The shell command if found, otherwise None.
        """
        
        res = strict_json(system_prompt = "Your job is to find out if there are instructions to run any shell commands",
                            user_prompt = aider_agent_response,
                            output_format = {'execute': 'Whether there are shell commands to execute, type: bool'},
                            llm = self.llm)
        
        if not res['execute']:
            return None

        sgpt_prompt = '''Provide only {shell} commands for {os} without any description.
If there is a lack of details, provide most logical solution.
Ensure the output is a valid shell command.
If multiple steps required try to combine them together using &&.
Provide only plain text without Markdown formatting.
Do not provide markdown formatting such as ```.
'''.format(shell = self.shell, os=self.os_name)

        res = strict_json(system_prompt = sgpt_prompt,
                            user_prompt = aider_agent_response,
                            output_format = {'command': 'Shell command to execute, type: str'},
                            llm = self.llm)

        return res['command']

    async def run_subtask(self, subtask: str) -> AsyncGenerator[str, None]:
        """
        Run a subtask using the main Aider agent.

        :param subtask: The subtask to run.
        :return: An async generator yielding parts of the response.
        """

        async for partial_response in self.find_relevant_code(subtask):
             yield partial_response

        for repo_path in self.aider_agents:
            code_snippet_filename = f"code_snippets_{repo_path.replace('/', '').replace('.','')}.txt"
            try:
                #shutil.move(f"{repo_path}/{code_snippet_filename}", f"{code_snippet_filename}")
                self.main_aider_agent.run(f"/read-only {code_snippet_filename}")
            except:
                print(f"error: {code_snippet_filename} not found, skipping")

        completed_tasks = ""

        if len(self.completed_subtasks) > 0:
            completed_tasks = "These are the tasks that you have already completed:\n"
            completed_tasks += "\n".join([f"{j+1}: {t}" for j, t in enumerate(self.completed_subtasks)])
        
        message = ""
        if len(self.completed_subtasks) > 0:
            message = f"""{completed_tasks}

Based on the above completed tasks, you are to complete the following task:
{subtask}

If the files you wish to write to do not exist yet, automatically create them.
"""
        else:
            message = f"""{completed_tasks}

You are to complete the following task:
{subtask}

If the files you wish to write to do not exist yet, automatically create them.
If you wish to edit a file, add the file to the chat.
"""
        response = ""

        async for partial_response in self.main_aider_agent.run_stream(message):
            response += partial_response
            yield partial_response

        self.completed_subtasks.append(subtask)

        #responses.append(response)

        '''cmd = self.check_for_shell_cmds_in_response(response)
        #print(cmd)
        if cmd is not None:
            #responses.append("<cmd>" + cmd)
            yield "\n<suggested_cmd>"
            #cmd_response = self.main_aider_agent.run_cmd(message)
            #yield cmd_response
            yield cmd
            yield "</suggested_cmd>\n"'''
            
        return

    def undo_last_subtask(self) -> str:
        """
        Undo the last completed subtask.

        :return: The result of the undo operation.
        """
        if len(self.completed_subtasks):
            self.completed_subtasks.pop()
            result = self.main_aider_agent.run('/undo')
            return result
        else:
            return "error: no previously completed subtasks"

    async def confirm_run_subtasks(self, subtasks: list[str]) -> AsyncGenerator[str, None]:
        """
        Confirm and run the generated subtasks.

        :param subtasks: The list of subtasks to run.
        :return: An async generator yielding parts of the response.
        """

        responses = []
        for subtask in subtasks:
            response = ""
            async for partial_response in self.run_subtask(subtask):
                response += partial_response
                yield partial_response
            responses.append(response)
        
        #return responses

    def get_agents(self) -> str:
        """
        Get a list of all initialized Aider agents.

        :return: A string representation of the agents.
        """
        return str(self.aider_agents)

manager = Manager()

# create agent
@app.post("/init_aider_agent")
async def init_aider_agent(repo_dir="."):
    """
    API endpoint to initialize an Aider agent.

    :param repo_dir: The directory of the repository.
    :return: The result of the initialization.
    """
    result = manager.init_aider_agent(repo_dir)
    return result

# get agents
@app.get("/get_agents")
async def get_agents():
    """
    API endpoint to get a list of all initialized Aider agents.

    :return: The result containing the list of agents.
    """
    return str(manager.get_agents())

# generate subtasks
@app.post("/generate_subtasks")
async def generate_subtasks(objective) -> list[str]:
    """
    API endpoint to generate subtasks for a given objective.

    :param objective: The main objective.
    :return: The list of generated subtasks.
    """
    return manager.generate_subtasks(objective)

# finetune subtasks
@app.post("/finetune_subtasks")
async def finetune_subtasks(objective, instruction):
    """
    API endpoint to finetune the generated subtasks based on additional instructions.

    :param objective: The main objective.
    :param instruction: Additional instructions for finetuning.
    :return: The result of the finetuning.
    """
    return manager.finetune_subtasks(objective, instruction)

@app.post("/run_subtask")
async def run_subtask(subtask):
    """
    API endpoint to run a subtask.

    :param subtask: The subtask to run.
    :return: The result of running the subtask.
    """
    return StreamingResponse(manager.run_subtask(subtask))

@app.get("/undo_last_subtask")
def undo_last_subtask():
    """
    API endpoint to undo the last completed subtask.

    :return: The result of the undo operation.
    """
    return manager.undo_last_subtask()

# confirm run subtasks
@app.post("/confirm_run_subtasks")
async def confirm_run_subtasks(subtasks: list[str]) -> list[str]:
    """
    API endpoint to confirm and run the generated subtasks.

    :param subtasks: The list of subtasks to run.
    :return: The list of responses from running the subtasks.
    """
    return StreamingResponse(manager.confirm_run_subtasks(subtasks))


def main() -> None:
    """
    Main function to run the application.
    """
    parser = argparse.ArgumentParser(description="Run the Aider agent manager.")
    parser.add_argument('--port', type=int, help='Port of the agent', default=10000)
    args = parser.parse_args()

    global START_PORT
    START_PORT = args.port + 1

    manager.init_planner_agent()
    manager.init_main_aider_agent()

    import uvicorn  # Import Uvicorn for running the FastAPI app
    uvicorn.run(app, host="0.0.0.0", port=args.port)

# Run the application with Uvicorn
if __name__ == "__main__":
    main()
