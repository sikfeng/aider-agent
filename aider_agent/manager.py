'''
TODO
------
Planning agent doesnt take into account the current state of the repo, so it might generate tasks that are already completed
External repo agents can be run simultaneously
Prompt tuning
Decide whether to use http or websockets
Better error handling
Shutdown uvicorn gracefully
'''

from aider.coders import Coder
from aider.models import Model
from aider.io import InputOutput

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

import argparse

import subprocess
import requests
import logging

import asyncio

import os
import signal
import platform
from distro import name as distro_name

import litellm
from litellm import acompletion, completion

litellm.suppress_debug_info = True
litellm.set_verbose = False
litellm.drop_params = True

from strictjson import *

from typing import AsyncGenerator
from pathlib import Path

import json
import re

from . import utils

app = FastAPI()

# TODO: better way of managing ports of aider instances
START_PORT = -1

class ExternalRepoAgent():
    """
    A class to manage an Aider instance initialized on another repository.
    """
    repo_dir: str = "."  # Directory of the repository
    port: int = -1  # Port number for the agent
    logger: logging.Logger  # Logger instance for the agent
    _process: subprocess.Popen | None = None  # Subprocess for the agent

    def __init__(self, repo_dir: str, model_name: str = "azure/gpt-4o", max_concurrent_llm_queries: int = 3) -> None:
        """
        Initialize the AiderAgent.

        :param model_name: The name of the model to use.
        :param repo_dir: The directory of the repository.
        :param max_concurrent_llm_queries: The maximum number of concurrent LLM queries.
        """

        # Standardize to use absolute path
        self.repo_dir = utils.get_absolute_path(repo_dir)
        self.logger = logging.getLogger(f"agent {self.repo_dir}")
        self.model_name = model_name
        self.max_concurrent_llm_queries = max_concurrent_llm_queries

        global START_PORT
        while True:
            self._process = subprocess.Popen(f"exec init_aider_instance --port {START_PORT} --model-name {model_name}", cwd=self.repo_dir, shell=True)
            self.logger.info(f"Attempt to start an aider instance on port {START_PORT} with model {model_name}")
            self.port = START_PORT
            START_PORT += 1
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if self._process.returncode is None:
                    self.logger.info(f"aider instance on port {START_PORT} still running, assuming successful")
                    # TODO: send a ping to check if the agent is alive
                    # TODO: perform this asynchronously rather than waiting
                    break
                self.logger.info(f"aider instance on port {START_PORT} terminated, continue trying...")
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
        # TODO: can use the ping method first instead
        poll = self._process.poll()
        if poll == None:
            return "alive"
        else:
            return "dead"
        
    def get_repo_map(self) -> str:
        response = requests.get(
            f"http://0.0.0.0:{self.port}/get_repo_map"
        )
        return response.json()

    async def find_relevant_code(self, task):
        # Step 1: Get list of relevant files
        system_msg = """
You are a software developer maintaining a project.
You are providing code snippets to a user who is working on a different project. 
The user will integrate the code snippets into their project to achieve a task.

Here are summaries of some files present in your project.

{repo_map}
        """
        repo_map = self.get_repo_map()
        system_msg = system_msg.format(repo_map=repo_map)

        user_msg = """
Please look through the repository structure and suggest a list of files that is relevant to the following task.

{task}

Please only provide the full path and return at most 5 files.
"""

        user_msg = user_msg.format(task=task)

        res = strict_json(
            system_prompt = system_msg,
            user_prompt = user_msg,
            output_format = {
                'filenames': "Array of filenames which contain relevant for completing the user's task, type: Array[str]"
            },
            llm = utils.llm(self.model_name)
        )

        # Ensure that the filenames were not hallucinated
        filenames = [filename for filename in res["filenames"] if (Path(self.repo_dir) / filename).is_file()]
        if len(filenames) == 0:
            # No real file names were generated, we should end early
            return

        # Step 2: Get the relevant definitions
        system_msg = """
You are a software developer maintaining a project.
You are providing code snippets to a user who is working on a different project. 
The user will integrate the code snippets into their project to achieve a task.

Here are summaries of some files present in your project.

{repo_map}
"""
        system_msg = system_msg.format(repo_map=repo_map)

        user_msg = """
Here are the files which the contain relevant code snippets.

{filenames}

For each of the above files, look through the repository structure to suggest the relevant class or functions that can be used for the following task.

{task}
"""

        task = "Create a new command in the package.json file that will trigger the webview."
        user_msg = user_msg.format(task=task, filenames=", ".join(f"`{filename}`" for filename in filenames))

        res = strict_json(
            system_prompt = system_msg,
            user_prompt = user_msg,
            output_format = {
                filename: f"Array of relevant class and method names in {filename}, type: Array[str]" for filename in filenames
            },
            llm = utils.llm(self.model_name)
        )

        useful_defs = {filename: res[filename] for filename in res if len(res[filename]) > 0}
        if len(useful_defs) == 0:
            # No useful defs found, we can stop early
            return
        
        # Step 3: Get the code snippets that were requested, and do one more round of checking if they are actually relevant
        # Create a semaphore with a limit of 3
        semaphore = asyncio.Semaphore(self.max_concurrent_llm_queries)

        async def process_file(filename, semaphore):
            async with semaphore:
                system_msg = """
You are a software developer maintaining a project.
You are providing code snippets to a user who is working on a different project. 
The user will integrate the code snippets into their project to achieve a task.

Here are the contents of {filename}:

```
{file_contents}
```
"""
                with open(Path(self.repo_dir) / filename) as f:
                    file_contents = f.read()
                    system_msg = system_msg.format(filename=filename, file_contents=file_contents)

                user_msg = """
For the following class, method and function names, extract their code from the file contents.
Also, determine if the code snippet will be useful, and if so explanation of why they are useful for the task.

Class/Method/Function names:
{definitions}

Task:
{task}
"""

                user_msg = user_msg.format(definitions=", ".join(f"`{def_name}`" for def_name in useful_defs[filename]), task=task)

                res = await strict_json_async(
                    system_prompt=system_msg,
                    user_prompt=user_msg,
                    output_format={
                        def_name: {
                            "code": f"code for `{def_name}`, type: code",
                            "useful": f"whether `{def_name}` is useful, type: bool",
                            "description": f"explanation of why `{def_name}` is useful for the task, type: str"
                        } for def_name in useful_defs[filename]
                    },
                    llm=utils.llm_async(self.model_name)
                )
                return {def_name: res[def_name] for def_name in res if res[def_name]["useful"]}

        tasks = [process_file(filename, semaphore) for filename in useful_defs]
        results = await asyncio.gather(*tasks)

        useful_codes = {filename: result for filename, result in zip(useful_defs, results) if len(result) > 0}

        response = ""
        for filename in useful_codes:
            for def_name in useful_codes[filename]:
                response += f"### {filename}\n{useful_codes[filename][def_name]['description']}\n\n"
                response += "```\n"
                response += useful_codes[filename][def_name]["code"]
                response += "\n```\n\n"
        response = response.strip()

        code_snippet_filename = f"code_snippets_{self.repo_dir.replace('/', '').replace('.','')}.txt"
        with open(code_snippet_filename, 'w') as code_snippet_file:
            code_snippet_file.write(response)

        return

    def kill(self):
        self._process.kill()
        return

class MainAiderAgent():
    """
    A class to manage the Aider agent.
    """
    coder = None

    def __init__(self, model_name: str = "azure/gpt-4o", repo_dir: str = ".") -> None:
        """
        Initialize the AiderAgent.

        :param model_name: The name of the model to use.
        :param repo_dir: The directory of the repository.
        """

        self.model_name = model_name
        self.model = Model(self.model_name)

        self.io = InputOutput(
            pretty=False,
            yes=True,
        )
        self.coder = Coder.create(
            main_model=self.model,
            io=self.io,
            suggest_shell_commands=False
        )
        return


    def run(self, msg: str) -> str:
        """
        Run the agent with the given message.

        :param msg: The message to process.
        :return: The result of processing the message.
        """
        try:
            result = self.coder.run("/code " + msg)
            return str(result)
        except:
            return "error: failed"

    def run_stream(self, msg: str):
        """
        Run the agent with the given message and stream the response.

        :param msg: The message to process.
        :return: An async generator yielding parts of the response.
        """
        for partial_response in self.coder.run_stream("/code " + msg):
            yield partial_response
        #return self.coder.run_stream(msg)

    def ask(self, msg: str):
        """
        Ask a question to the Aider agent.

        :param msg: The question to ask.
        :return: The response from the agent.
        """
        return self.run_stream("/ask " + msg)

    def run_cmd(self, cmd: str) -> str:
        """
        Run a command using the Aider agent.

        :param cmd: The command to run.
        :return: The response from the agent.
        """
        return self.run("/run " + cmd)

    def get_repo_map(self) -> str:
        return self.coder.get_repo_map()


class PlannerAgent():
    """
    A class to manage the Planner agent.
    """
    def __init__(self, model_name: str = "azure/gpt-4o", map_tokens=8092, max_concurrent_llm_queries=2) -> None:
        """
        Initialize the PlannerAgent.

        :param model_name: The name of the model to use.
        """
        self.model_name = model_name
        self.logger = logging.getLogger("planner")
        self.map_tokens = map_tokens
        self.max_concurrent_llm_queries = max_concurrent_llm_queries
        return

    async def gather_information(self, objective: str) -> dict:
        """
        Gather necessary information to generate a plan for the given objective.

        :param objective: The main objective.
        :return: A dictionary containing the gathered information.
        """
        # Ask the LLM what questions to ask using strictjson
        system_prompt = """
You are a software engineer gathering information to complete a task. However, you suspect that some functionality has already been implemented, which you can reuse.

There is another software developer which understands the codebase which you will work on.

You will ask questions to find out how you can reuse existing functionality to complete your task.
You should consider the subtasks which you will have to implement, and ask the developer questions relating to those subtasks.
"""
        user_prompt = """
What information do you need to know to complete the following task? Give at most 10 questions.
Each question should be clear and specific to the task and codebase you are working on.

{objective}
"""
        user_prompt = user_prompt.format(objective=objective)
        questions_response = strict_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_format={'questions': 'Array of questions, type: Array[str]'},
            llm=utils.llm(self.model_name)
        )

        questions = questions_response['questions']

        def ask_aider(question: str) -> str:
            model = Model(self.model_name)
            with open(os.devnull, "w") as output:
                io = InputOutput(
                    pretty=False,
                    yes=True,
                    output=output
                )
                coder = Coder.create(
                    main_model=model,
                    io=io,
                    suggest_shell_commands=False,
                    edit_format="ask",
                    map_tokens=self.map_tokens,
                )
                coder.run("""What files do you need to answer the following question?
{question}

Return the files in the format as such.
```
file1.py
file2.js
file3.json
```
""".format(question=question))
                coder.done_messages = []
                coder.cur_messages = []
                response = coder.run("""{question}

Do NOT write any code for implementing any features. 
Only respond in natural language.
Only respond with information about the current codebase.
Respond with a high level overview of what has already been implemented, and what is missing.
""")
                return question, response

        async def limited_ask_aider(semaphore, question):
            async with semaphore:
                return await asyncio.to_thread(ask_aider, question)

        semaphore = asyncio.Semaphore(self.max_concurrent_llm_queries)

        gathered_info = {}
        tasks = [limited_ask_aider(semaphore, question) for question in questions]
        responses = await asyncio.gather(*tasks)

        for question, response in responses:
            gathered_info[question] = response

        #print(gathered_info)
        return gathered_info

    # TODO: I tried getting it to incorporate codebase context when planning, but its not working well
    # if the user asks to implement a whole feature, it may still plan some subtasks that are already completed
    # and with more prompts its getting slower
    async def generate_subtasks(self, objective: str) -> list[str]:
        """
        Generate a list of subtasks to achieve the given objective.

        :param objective: The main objective.
        :return: A list of subtasks.
        """
        # Restate the problem statement
        system_msg = """You are a requirements analyst.
Restate the following as an instruction for a software developer
"""
        user_msg = objective
        objective = utils.llm(self.model_name)(
            system_prompt=system_msg, user_prompt=user_msg
        )

        system_msg = """You're a diligent software engineer AI.

Create a plan consisting of multiple tasks to complete the provided objective.

Each task should be a discrete, actionable step that contributes to the overall objective.
Do not waste time on uneccessary or redundant steps.
Don't create needless tasks like "document the findings".

These tasks will be given to a new intern developer, hence ensure each task has a clear description.

Here are some questions and answers regarding this codebase.
{gathered_info}

Do not implement functionality that the user did not ask for, or is already implemented.
Building, testing and deployment are not required, so do not plan these tasks.
"""


        # Gather necessary information
        gathered_info = await self.gather_information(objective)

        # Format gathered_info in markdown
        formatted_gathered_info = ""
        
        for question, answer in gathered_info.items():
            formatted_gathered_info += """**Question:** 
{question}

**Answer:**
{answer}
""".format(question=question, answer=answer)

        system_msg = system_msg.format(gathered_info=formatted_gathered_info)
        print(system_msg)

        res = strict_json(
            system_prompt = system_msg,
            user_prompt = objective,
            output_format = {'Plan': 'Array of subtasks, type: Array[str]'},
            llm = utils.llm(self.model_name)
        )
        
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
    def __init__(self, model_name:str = "azure/gpt-4o", max_reflections=5) -> None:
        """
        Initialize the Manager.
        """
        self.planner_agent = None
        self.main_aider_agent = None
        self.external_repo_agents = dict()
        self.logger = logging.getLogger("manager")
        self.model_name = model_name
        self.max_reflections = max_reflections

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

    def init_external_repo_agent(self, repo_dir: str, model_name="azure/gpt-4o") -> str:
        """
        Initialize an Aider agent.

        :param repo_dir: The directory of the repository.
        :return: "success" if the agent is initialized, otherwise an error message.
        """
        repo_dir = utils.get_absolute_path(repo_dir)
        if repo_dir in self.external_repo_agents:
            return "error: agent already initialized on this repo dir"
        
        agent = ExternalRepoAgent(model_name=model_name, repo_dir=repo_dir)

        self.external_repo_agents[repo_dir] = agent
        return "success"
    
    def init_main_aider_agent(self, model_name="azure/gpt-4o") -> str:
        """
        Initialize the main Aider agent.

        :return: "success" if the agent is initialized.
        """
        agent = MainAiderAgent(model_name=model_name)

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

    async def generate_subtasks(self, objective: str) -> list[str]:
        """
        Generate a list of subtasks to achieve the given objective.

        :param objective: The main objective.
        :return: A list of subtasks.
        """
        return await self.planner_agent.generate_subtasks(objective)
        
    def finetune_subtasks(self, objective: str, instruction: str) -> list[str]:
        return "TODO"

    async def run_subtask(self, subtask: str) -> AsyncGenerator[str, None]:
        """
        Run a subtask using the main Aider agent.

        :param subtask: The subtask to run.
        :return: An async generator yielding parts of the response.
        """

        await asyncio.gather(*(external_repo_agent.find_relevant_code(subtask) for external_repo_agent in self.external_repo_agents.values()))

        for repo_path in self.external_repo_agents:
            code_snippet_filename = f"code_snippets_{repo_path.replace('/', '').replace('.','')}.txt"
            print(code_snippet_filename)
            try:
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
        for _ in range(self.max_reflections):
            curr_response = ""
            for partial_response in self.main_aider_agent.run_stream(message):
                curr_response += partial_response
                yield partial_response

            response += curr_response

            # Check for shell commands and files to add in the response
            def check_for_shell_cmds_in_response(aider_agent_response: str) -> str | None:
                """
                Check if there are shell commands in the Aider agent response.

                :param aider_agent_response: The response from the Aider agent.
                :return: The shell command if found, otherwise None.
                """
                # List of shell code block markers
                shell_markers = [
                    "bash", "sh", "shell", "cmd", "batch", "powershell", "ps1",
                    "zsh", "fish", "ksh", "csh", "tcsh"
                ]
                
                # Create a regex pattern to match any of the shell code block markers
                shell_code_pattern = re.compile(
                    r'```(?:' + '|'.join(shell_markers) + r')(.*?)```', re.DOTALL | re.IGNORECASE
                )

                # Find all matches
                matches = shell_code_pattern.findall(aider_agent_response)

                if not matches:
                    return None
                
                return shell_cmds

            # Check for shell commands and files to add in the response
            shell_cmds = check_for_shell_cmds_in_response(curr_response)

            if shell_cmds is not None:
                for command in shell_cmds:
                    yield f"\n<suggested_cmd>{command}</suggested_cmd>\n"
                    # Optionally, you can execute the command here if needed
                    #cmd_response = self.main_aider_agent.run_cmd(command)
                    #yield f"<cmd_response>{cmd_response}</cmd_response>"

            # Use the new function to find files to add

            if self.main_aider_agent.coder.reflected_message is None:
                break
            else:
                message = self.main_aider_agent.coder.reflected_message

        self.completed_subtasks.append(subtask)

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

    def get_external_repo_agents(self) -> list[str]:
        """
        Get a list of all initialized Aider agents.

        :return: A string representation of the agents.
        """
        return list(self.external_repo_agents.keys())
    
    def shutdown(self):
        for external_repo_agent in self.external_repo_agents.values():
            external_repo_agent.kill()
        return "shutdown"

manager = Manager()

# create agent
@app.post("/init_external_repo_agent")
async def init_external_repo_agent(repo_dir):
    """
    API endpoint to initialize an Aider agent.

    :param repo_dir: The directory of the repository.
    :return: The result of the initialization.
    """
    result = manager.init_external_repo_agent(repo_dir)
    return result

@app.get("/get_external_repo_agents")
async def get_external_repo_agents() -> list[str]:
    """
    API endpoint to get a list of all initialized Aider agents.

    :return: The result containing the list of agents.
    """
    return manager.get_external_repo_agents()

# generate subtasks
@app.post("/generate_subtasks")
async def generate_subtasks(objective) -> list[str]:
    """
    API endpoint to generate subtasks for a given objective.

    :param objective: The main objective.
    :return: The list of generated subtasks.
    """
    return await manager.generate_subtasks(objective)

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

@app.get("/shutdown")
def shutdown():
    manager.shutdown()
    os.kill(os.getpid(), signal.SIGTERM)
    return "shutdown"

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
