import logging
import subprocess
import time
import httpx
import asyncio
from pathlib import Path
from typing import AsyncGenerator
from . import utils

from strictjson import *


class InitExternalRepoAgentError(RuntimeError):
    pass


class ExternalRepoAgent():
    """
    A class to manage an Aider instance initialized on another repository.
    """
    repo_dir: str = "."  # Directory of the repository
    port: int = -1  # Port number for the agent
    logger: logging.Logger  # Logger instance for the agent
    _process: subprocess.Popen | None = None  # Subprocess for the agent

    def __init__(
            self,
            repo_dir: str,
            model_name: str = "azure/gpt-4o",
            max_concurrent_llm_queries: int = 3,
            max_init_retry=5) -> None:
        """
        Initialize the AiderAgent.

        :param model_name: The name of the model to use.
        :param repo_dir: The directory of the repository.
        :param max_concurrent_llm_queries: The maximum number of concurrent LLM queries.
        """

        # Standardize to use absolute path
        self.repo_dir = utils.get_absolute_path(repo_dir)
        self.logger = logging.getLogger(
            f"ExternalRepoAgent: `{self.repo_dir}`")
        self.model_name = model_name
        self.max_concurrent_llm_queries = max_concurrent_llm_queries
        self.code_snippet_filename = utils.get_absolute_path(
            f"code_snippets_{self.repo_dir.replace('/', '').replace('.','')}.txt")

        def get_free_port():
            import socket
            sock = socket.socket()
            sock.bind(('', 0))
            port = sock.getsockname()[1]
            sock.close()
            return port

        # TODO: repomaps may take much longer to build if aider has never been initialized on the repo before
        # Current implementation just kills the process and continues after reaching timeout
        # One possible fix is to increase the timeout or remove it, but can I
        # guarantee that it will always succeed if it doesnt terminate?

        for _ in range(max_init_retry):
            self.port = get_free_port()
            self.logger.info(
                f"Attempt to start an aider instance on port {self.port} with model {model_name}")
            self._process = subprocess.Popen(
                f"exec init_aider_instance --port {self.port} --model-name {model_name}",
                cwd=self.repo_dir,
                shell=True)
            ping_success = self.wait_for_ping()
            if ping_success:
                self.logger.info(
                    f"aider instance on port {self.port} returned ping, successful init")
                break
            else:
                if self._process.poll() is None:
                    self._process.kill()
                self.logger.warning(
                    f"aider instance on port {self.port} killed, continue trying...")
        else:
            # Exhausted retries
            raise InitExternalRepoAgentError(
                f"Failed to initialize ExternalRepoAgent on {self.repo_dir}")

    def wait_for_ping(self) -> bool:
        """
        Wait for the Aider agent to respond with "pong" to a ping request.

        :return: True if the agent responds with "pong", False if timeout is reached.
        """
        timeout = 6
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = httpx.get(f"http://0.0.0.0:{self.port}/ping")
                if response.json() == "pong":
                    return True
            except httpx.RequestError as e:
                self.logger.warn(f"Ping request failed: {e}")
            time.sleep(1)  # Wait for 0.5 seconds before retrying
        return False

    def run(self, msg: str) -> str:
        """
        Send a message to the Aider agent.

        :param msg: The message to send.
        :return: The response from the agent.
        """
        response = httpx.post(
            f"http://0.0.0.0:{self.port}/msg",
            params={"msg": msg},
        )
        return response.json()["result"]

    async def run_stream(
            self, msg: str, chunk_size: int = 64) -> AsyncGenerator[str, None]:
        """
        Send a message to the Aider agent and stream the response.

        :param msg: The message to send.
        :param chunk_size: The size of each chunk in the stream.
        :return: An async generator yielding parts of the response.
        """
        response = httpx.post(
            f"http://0.0.0.0:{self.port}/run_stream",
            params={"msg": msg},
            stream=True
        )
        # return response.json()["result"]
        for partial_response in response.iter_content(
                chunk_size=chunk_size, decode_unicode=True):
            if isinstance(partial_response, bytes):
                partial_response = partial_response.decode('utf-8')
            yield partial_response

    async def ask(self, msg: str,
                  chunk_size: int = 64) -> AsyncGenerator[str, None]:
        """
        Ask a question to the Aider agent.

        :param msg: The question to ask.
        :return: The response from the agent.
        """
        response = httpx.post(
            f"http://0.0.0.0:{self.port}/ask",
            params={"msg": msg},
            stream=True
        )
        for partial_response in response.iter_content(
                chunk_size=chunk_size, decode_unicode=True):
            if isinstance(partial_response, bytes):
                partial_response = partial_response.decode('utf-8')
            yield partial_response

    def run_cmd(self, cmd: str) -> str:
        """
        Run a command using the Aider agent.

        :param cmd: The command to run.
        :return: The response from the agent.
        """
        response = httpx.post(
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
        if poll is not None:
            return "dead"

        ping_response = httpx.get(
            f"http://0.0.0.0:{self.port}/ping"
        )
        if ping_response == "pong":
            return "alive"

        return "dead"

    def get_repo_map(self) -> str:
        response = httpx.get(
            f"http://0.0.0.0:{self.port}/get_repo_map"
        )
        return response.json()

    async def find_relevant_code(self, task):
        Path.unlink(Path(self.code_snippet_filename), missing_ok=True)

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
            system_prompt=system_msg,
            user_prompt=user_msg,
            output_format={
                'filenames': "Array of filenames which contain relevant for completing the user's task, type: Array[str]"
            },
            llm=utils.llm(self.model_name)
        )

        # Ensure that the filenames were not hallucinated
        filenames = [filename for filename in res["filenames"]
                     if (Path(self.repo_dir) / filename).is_file()]
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
        user_msg = user_msg.format(
            task=task, filenames=", ".join(
                f"`{filename}`" for filename in filenames))

        res = strict_json(
            system_prompt=system_msg,
            user_prompt=user_msg,
            output_format={
                filename: f"Array of relevant class and method names in {filename}, type: Array[str]" for filename in filenames
            },
            llm=utils.llm(self.model_name)
        )

        useful_defs = {filename: res[filename]
                       for filename in res if len(res[filename]) > 0}
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
                    system_msg = system_msg.format(
                        filename=filename, file_contents=file_contents)

                user_msg = """
For the following class, method and function names, extract their code from the file contents.
Also, determine if the code snippet will be useful, and if so explanation of why they are useful for the task.

Class/Method/Function names:
{definitions}

Task:
{task}
"""

                user_msg = user_msg.format(
                    definitions=", ".join(
                        f"`{def_name}`" for def_name in useful_defs[filename]),
                    task=task)

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
                return {def_name: res[def_name]
                        for def_name in res if res[def_name]["useful"]}

        tasks = [process_file(filename, semaphore) for filename in useful_defs]
        results = await asyncio.gather(*tasks)

        useful_codes = {
            filename: result for filename,
            result in zip(
                useful_defs,
                results) if len(result) > 0}

        response = ""
        for filename in useful_codes:
            for def_name in useful_codes[filename]:
                response += f"{filename}\n{useful_codes[filename][def_name]['description']}\n\n"
                response += "```\n"
                response += useful_codes[filename][def_name]["code"]
                response += "\n```\n\n"
        response = response.strip()

        with open(self.code_snippet_filename, 'w') as code_snippet_file:
            code_snippet_file.write(response)

        return

    def kill(self):
        self._process.kill()
        return
