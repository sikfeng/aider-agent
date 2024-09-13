import logging
import subprocess
import time
import httpx
import asyncio
from pathlib import Path
from typing import AsyncGenerator
from . import utils
from .prompts import ExternalRepoAgentHandlerPrompts

from strictjson import *
import litellm


class InitExternalRepoAgentError(RuntimeError):
    pass


class ExternalRepoAgentHandler():
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
            max_concurrent_llm_queries: int = 1,
            max_init_retry=5) -> None:
        """
        Initialize the AiderAgent.

        :param model_name: The name of the model to use.
        :param repo_dir: The directory of the repository.
        :param max_concurrent_llm_queries: The maximum number of concurrent LLM queries.
        """

        if not Path(repo_dir).is_dir():
            self.logger.error(
                f"Attempt to initialize ExternalRepoAgent on non-existent directory {repo_dir}.")
            raise FileNotFoundError

        # Standardize to use absolute path
        self.repo_dir = utils.get_absolute_path(repo_dir)
        self.logger = logging.getLogger(
            f"ExternalRepoAgent: {self.repo_dir}")
        self.model_name = model_name
        # TODO: assert that this value is sensible
        self.max_concurrent_llm_queries = max_concurrent_llm_queries
        self.code_snippet_filename = utils.get_absolute_path(
            f"code_snippets_{self.repo_dir.replace('/', '').replace('.','')}.txt")

        def get_free_port():
            # TODO: handle potential errors
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
                f"Attempt to start an aider instance on port {self.port} with model {model_name}.")
            self._process = subprocess.Popen(
                f"exec init_repo_agent --port {self.port} --model-name {model_name}",
                cwd=self.repo_dir,
                shell=True)
            ping_success = self.wait_for_ping()
            if ping_success:
                self.logger.info(
                    f"Aider instance on port {self.port} returned ping, successfully initialized.")
                break
            else:
                if self._process.poll() is None:
                    self._process.kill()
                self.logger.warning(
                    f"Attempt to start Aider instance on port {self.port} killed.")
        else:
            # Exhausted retries
            self.logger.error(
                f"Aider instance failed to initialize within {max_init_retry} tries, quitting.")
            raise InitExternalRepoAgentError(
                f"Failed to initialize ExternalRepoAgent on {self.repo_dir}.")

    def wait_for_ping(self) -> bool:
        """
        Wait for the Aider agent to respond with "pong" to a ping request.

        :return: True if the agent responds with "pong", False if timeout is reached.
        """
        self.logger.info("Waiting for ping response.")
        timeout = 6  # TODO: set as class variable
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = httpx.get(f"http://0.0.0.0:{self.port}/ping")
                if response.json() == "pong":
                    self.logger.info("Ping successful.")
                    return True
            except httpx.RequestError as e:
                self.logger.debug(f"Ping request failed: {e}")
            # TODO: set as class variable
            time.sleep(1)  # Wait for 1 second before retrying
        self.logger.warning("Ping timeout reached.")
        # raise TimeoutError
        return False

    def run(self, msg: str) -> str:
        """
        Send a message to the Aider agent.

        :param msg: The message to send.
        :return: The response from the agent.
        """
        self.logger.info(f"Sending message: {msg}")
        response = httpx.post(
            f"http://0.0.0.0:{self.port}/run",
            params={"msg": msg},
        )
        result = response.json()["result"]
        self.logger.debug(f"Received response: {result}")
        return result

    async def run_stream(
            self, msg: str, chunk_size: int = 64) -> AsyncGenerator[str, None]:
        """
        Send a message to the Aider agent and stream the response.

        :param msg: The message to send.
        :param chunk_size: The size of each chunk in the stream.
        :return: An async generator yielding parts of the response.
        """
        self.logger.info(f"Sending message for streaming: {msg}")
        response = httpx.post(
            f"http://0.0.0.0:{self.port}/run_stream",
            params={"msg": msg},
            stream=True
        )
        for partial_response in response.iter_content(
                chunk_size=chunk_size, decode_unicode=True):
            if isinstance(partial_response, bytes):
                partial_response = partial_response.decode('utf-8')
            self.logger.debug(f"Received partial response: {partial_response}")
            yield partial_response

    async def ask(self, msg: str,
                  chunk_size: int = 64) -> AsyncGenerator[str, None]:
        """
        Ask a question to the Aider agent.

        :param msg: The question to ask.
        :return: The response from the agent.
        """
        self.logger.info(f"Asking question: {msg}")
        response = httpx.post(
            f"http://0.0.0.0:{self.port}/ask",
            params={"msg": msg},
            stream=True
        )
        for partial_response in response.iter_content(
                chunk_size=chunk_size, decode_unicode=True):
            if isinstance(partial_response, bytes):
                partial_response = partial_response.decode('utf-8')
            self.logger.debug(f"Received partial response: {partial_response}")
            yield partial_response

    def run_cmd(self, cmd: str) -> str:
        """
        Run a command using the Aider agent.

        :param cmd: The command to run.
        :return: The response from the agent.
        """
        self.logger.info(f"Running command: {cmd}")
        response = httpx.post(
            f"http://0.0.0.0:{self.port}/msg",
            params={"msg": f"/run {cmd}"},
        )
        result = response.json()["result"]
        self.logger.info(f"Received command response: {result}")
        return result

    def get_repo_map(self) -> str:
        self.logger.info("Getting repository map")
        response = httpx.get(
            f"http://0.0.0.0:{self.port}/get_repo_map"
        )
        repo_map = response.json()
        self.logger.debug(f"Received repository map: {repo_map}")
        return repo_map

    async def find_relevant_code(self, task):
        self.logger.info(f"Finding relevant code for task: {task}")

        # Delete existing code snippet file if it exists
        Path.unlink(Path(self.code_snippet_filename), missing_ok=True)

        # Step 1: Get list of relevant files
        repo_map = self.get_repo_map()
        system_prompt = ExternalRepoAgentHandlerPrompts.SYSTEM_PROMPT_FIND_RELEVANT_FILENAMES.format(
            repo_map=repo_map)
        user_prompt = ExternalRepoAgentHandlerPrompts.USER_PROMPT_FIND_RELEVANT_FILENAMES.format(
            task=task)

        res = await utils.strict_json_retry(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
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
            self.logger.info("No relevant filenames found")
            return

        # Step 2: Get the relevant definitions
        system_prompt = ExternalRepoAgentHandlerPrompts.SYSTEM_PROMPT_FIND_RELEVANT_DEFINITIONS.format(
            repo_map=repo_map)
        user_prompt = ExternalRepoAgentHandlerPrompts.USER_PROMPT_FIND_RELEVANT_DEFINITIONS.format(
            task=task, filenames=", ".join(f"`{filename}`" for filename in filenames))

        res = await utils.strict_json_retry(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_format={
                filename: f"Array of relevant class and method names in {filename}, type: Array[str]" for filename in filenames
            },
            llm=utils.llm(self.model_name)
        )

        useful_defs = {filename: res[filename]
                       for filename in res if len(res[filename]) > 0}
        if len(useful_defs) == 0:
            # No useful defs found, we can stop early
            self.logger.info("No useful definitions found")
            return

        # TODO: consider using static analysis to extract the codes instead
        # Step 3: Get the code snippets that were requested, and do one more round of checking if they are actually relevant
        # Create a semaphore to limit concurrent queries
        semaphore = asyncio.Semaphore(self.max_concurrent_llm_queries)

        async def process_file(filename, semaphore):
            async with semaphore:
                system_prompt = ""
                with open(Path(self.repo_dir) / filename) as f:
                    file_contents = f.read()
                    system_prompt = ExternalRepoAgentHandlerPrompts.SYSTEM_PROMPT_PROCESS_FILE.format(
                        filename=filename, file_contents=file_contents)

                user_prompt = ExternalRepoAgentHandlerPrompts.USER_PROMPT_PROCESS_FILE.format(
                    definitions=", ".join(f"`{def_name}`" for def_name in useful_defs[filename]),
                    task=task
                )

                user_prompt = user_prompt.format(
                    definitions=", ".join(
                        f"`{def_name}`" for def_name in useful_defs[filename]),
                    task=task)

                res = await utils.strict_json_async_retry(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
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

        self.logger.info("Relevant code snippets written to file")

        return

    def kill(self):
        """
        Kill the Aider agent process.
        """
        self.logger.info("Killing process")
        self._process.kill()
        return
