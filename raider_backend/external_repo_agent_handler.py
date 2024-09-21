"""
This module provides the ExternalRepoAgentHandler class and related
functionality.

The ExternalRepoAgentHandler class is responsible for managing an
Aider instance initialized on another repository. It handles the
initialization, communication, and termination of the Aider agent
process. The class also provides methods to send messages, run
commands, and find relevant code snippets in the repository.
"""
import logging
import subprocess
import time
import asyncio
from pathlib import Path
from typing import AsyncGenerator
import socket

import httpx

from . import utils
from . import parse
from .prompts import ExternalRepoAgentHandlerPrompts


class InitExternalRepoAgentError(RuntimeError):
    """
    Exception raised when the initialization of an ExternalRepoAgent
    fails.

    This exception is used to indicate that the ExternalRepoAgent could
    not be initialized after the specified number of retries. It
    typically occurs when the agent fails to start or respond to ping
    requests within the allowed time frame.
    """
    pass


class ExternalRepoAgentHandler():
    """
    A class to manage an Aider instance initialized on another
    repository.
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
            max_init_retry=3,
            timeout=10,
            agent_manager=None) -> None:
        """
        Initialize the AiderAgent.

        :param model_name: The name of the model to use.
        :param repo_dir: The directory of the repository.
        :param max_concurrent_llm_queries: The maximum number of
            concurrent LLM queries.
        :param agent_manager: The AgentManager instance.
        """

        if not Path(repo_dir).is_dir():
            self.logger.error(
                ("Attempt to initialize ExternalRepoAgent on "
                 "non-existent directory %s."),
                repo_dir)
            raise FileNotFoundError

        # Standardize to use absolute path
        self.repo_dir = utils.get_absolute_path(repo_dir)
        self.logger = logging.getLogger(
            f"ExternalRepoAgent: {self.repo_dir}")
        self.model_name = model_name
        self.agent_manager = agent_manager
        # TODO: assert that this value is sensible
        self.max_concurrent_llm_queries = max_concurrent_llm_queries
        self.code_snippet_filename = utils.get_absolute_path(
            f"code_snippets_{self.repo_dir.replace('/', '').replace('.','')}.txt")

        def get_free_port():
            # TODO: handle potential errors
            sock = socket.socket()
            sock.bind(('', 0))
            port = sock.getsockname()[1]
            sock.close()
            return port

        # TODO: repomaps may take much longer to build if aider has
        # never been initialized on the repo before
        # Current implementation just kills the process and continues
        # after reaching timeout
        # One possible fix is to increase the timeout or remove it, but
        # can I guarantee that it will always succeed if it doesnt
        # terminate?

        for _ in range(max_init_retry):
            self.port = get_free_port()
            self.logger.info(
                "Attempt to start an aider instance on port %s with model %s.",
                self.port,
                model_name)
            self._process = subprocess.Popen(
                (f"exec init_repo_agent --port {self.port} "
                 f"--model-name {model_name}"),
                cwd=self.repo_dir,
                shell=True)
            ping_success = self.wait_for_ping(timeout=timeout)
            if ping_success:
                self.logger.info(
                    ("Aider instance on port %s returned ping, successfully "
                     "initialized."),
                    self.port)
                break

            if self._process.poll() is None:
                self._process.kill()
            self.logger.warning(
                "Attempt to start Aider instance on port %s killed.",
                self.port)
        else:
            # Exhausted retries
            self.logger.error(
                ("Aider instance failed to initialize within %s tries, "
                 "quitting."),
                max_init_retry)
            raise InitExternalRepoAgentError(
                f"Failed to initialize ExternalRepoAgent on {self.repo_dir}.")

    def wait_for_ping(self, timeout) -> bool:
        """
        Wait for the Aider agent to respond with "pong" to a ping
        request.

        :return: True if the agent responds with "pong", False if
            timeout is reached.
        """
        self.logger.info("Waiting for ping response.")
        timeout = timeout
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = httpx.get(f"http://0.0.0.0:{self.port}/ping")
                if response.json() == "pong":
                    self.logger.info("Ping successful.")
                    return True
            except httpx.RequestError as e:
                self.logger.debug("Ping request failed: %s", e)
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
        self.logger.info("Sending message: %s", msg)
        response = httpx.post(
            f"http://0.0.0.0:{self.port}/run",
            params={"msg": msg},
        )
        result = response.json()["result"]
        self.logger.debug("Received response: %s", result)
        return result

    async def run_stream(
            self, msg: str, chunk_size: int = 64) -> AsyncGenerator[str, None]:
        """
        Send a message to the Aider agent and stream the response.

        :param msg: The message to send.
        :param chunk_size: The size of each chunk in the stream.
        :return: An async generator yielding parts of the response.
        """
        self.logger.info("Sending message for streaming: %s", msg)
        response = httpx.post(
            f"http://0.0.0.0:{self.port}/run_stream",
            params={"msg": msg},
        )
        for partial_response in response.iter_content(
                chunk_size=chunk_size, decode_unicode=True):
            if isinstance(partial_response, bytes):
                partial_response = partial_response.decode('utf-8')
            self.logger.debug(
                "Received partial response: %s",
                partial_response)
            yield partial_response

    async def ask(self, msg: str,
                  chunk_size: int = 64) -> AsyncGenerator[str, None]:
        """
        Ask a question to the Aider agent.

        :param msg: The question to ask.
        :return: The response from the agent.
        """
        self.logger.info("Asking question: %s", msg)
        response = httpx.post(
            f"http://0.0.0.0:{self.port}/ask",
            params={"msg": msg},
        )
        for partial_response in response.iter_content(
                chunk_size=chunk_size, decode_unicode=True):
            if isinstance(partial_response, bytes):
                partial_response = partial_response.decode('utf-8')
            self.logger.debug(
                "Received partial response: %s",
                partial_response)
            yield partial_response

    def run_cmd(self, cmd: str) -> str:
        """
        Run a command using the Aider agent.

        :param cmd: The command to run.
        :return: The response from the agent.
        """
        self.logger.info("Running command: %s", cmd)
        response = httpx.post(
            f"http://0.0.0.0:{self.port}/msg",
            params={"msg": f"/run {cmd}"},
        )
        result = response.json()["result"]
        self.logger.info("Received command response: %s", result)
        return result

    def get_repo_map(self) -> str:
        """
        Retrieve the repository map from the Aider agent.

        This method sends a GET request to the Aider agent to obtain
        the repository map, which is a structured representation of the
        repository's contents. The repository map is useful for
        understanding the structure and organization of the codebase.

        :return: The repository map.
        """
        self.logger.info("Getting repository map")
        response = httpx.get(
            f"http://0.0.0.0:{self.port}/get_repo_map"
        )
        repo_map = response.json()
        self.logger.debug("Received repository map: %s", repo_map)
        return repo_map

    async def find_relevant_code(self, task):
        """
        Find relevant code snippets in the repository for a given task.

        This method performs a multi-step process to identify and
        retrieve code snippets that are relevant to the specified task.
        It involves the following steps:

        1. Retrieve a list of relevant files from the repository map.
        2. Identify relevant class, method, and function definitions
           within those files.
        3. Validate the relevance of the identified definitions using
           an LLM (Language Model).
        4. Write the relevant code snippets to a file for further use.

        :param task: A description of the task for which relevant code
            snippets are to be found.
        :return: None
        """
        self.logger.info("Finding relevant code for task: %s", task)

        # Delete existing code snippet file if it exists
        Path.unlink(Path(self.code_snippet_filename), missing_ok=True)

        # Step 1: Get list of relevant files
        self.logger.debug("Getting repository map")
        repo_map = self.get_repo_map()
        self.logger.debug("Repository map: %s", repo_map)

        system_prompt = ExternalRepoAgentHandlerPrompts.SYSTEM_PROMPT_FIND_RELEVANT_FILENAMES.format(
            repo_map=repo_map)
        user_prompt = ExternalRepoAgentHandlerPrompts.USER_PROMPT_FIND_RELEVANT_FILENAMES.format(
            task=task)

        self.logger.debug("Sending prompts to LLM to find relevant filenames")
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
        self.logger.debug("Relevant filenames found: %s", filenames)

        # Step 2: Get the relevant definitions
        self.logger.debug("Getting relevant definitions from filenames")
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
        self.logger.debug("Useful definitions found: %s", useful_defs)

        # Step 3: Get the code snippets that were requested, and do
        # one more round of checking if they are actually relevant
        # Create a semaphore to limit concurrent queries
        semaphore = asyncio.Semaphore(self.max_concurrent_llm_queries)

        async def process_file(filename, semaphore):
            self.logger.info("Processing file: %s", filename)

            # TODO: class, method and function defs are all processed
            # the same way right now
            class_defs, method_defs, function_defs = parse.get_class_method_function_defs(
                Path(self.repo_dir) / filename)
            if class_defs is None and method_defs is None and \
                    function_defs is None:
                self.logger.debug(
                    "No definitions parsed from file: %s", filename)
                return {}

            definition_codes = {}
            for def_name in useful_defs[filename]:
                if def_name in class_defs:
                    definition_codes[def_name] = class_defs[def_name]
                elif def_name in method_defs:
                    definition_codes[def_name] = method_defs[def_name]
                elif def_name in function_defs:
                    definition_codes[def_name] = function_defs[def_name]
                else:
                    self.logger.debug(
                        "Definition %s not found in file: %s",
                        def_name, filename)

            async with semaphore:
                formatted_defs = ""
                for def_name, def_code in definition_codes.items():
                    formatted_defs += f"""
`{def_name}` code:
```
{def_code}
```

"""
                system_prompt = ExternalRepoAgentHandlerPrompts.SYSTEM_PROMPT_PROCESS_FILE_FOR_DEFINITIONS.format(
                    formatted_defs=formatted_defs)
                user_prompt = ExternalRepoAgentHandlerPrompts.USER_PROMPT_PROCESS_FILE_FOR_DEFINITIONS.format(
                    task=task)

                self.logger.debug(
                    "Sending prompts to LLM for file: %s", filename)
                response = await utils.strict_json_async_retry(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    output_format={
                        def_name: {
                            "useful": f"whether `{def_name}` is useful, type: bool",
                            "description": f"explanation of why `{def_name}` is useful for the task, type: str"
                        } for def_name in definition_codes
                    },
                    llm=utils.llm_async(self.model_name)
                )

            result = {def_name: response[def_name]
                      for def_name in response if response[def_name]["useful"]}
            for def_name in result:
                result[def_name]["code"] = definition_codes[def_name]

            self.logger.info("Finished processing file: %s", filename)
            return result

        self.logger.debug("Creating tasks to process files")
        tasks = [process_file(filename, semaphore) for filename in useful_defs]
        results = await asyncio.gather(*tasks)

        useful_codes = {
            filename: result for filename,
            result in zip(
                useful_defs,
                results) if len(result) > 0}

        if not useful_codes:
            self.logger.info("No useful code snippets found")
            return

        self.logger.debug("Useful codes found: %s", useful_codes)

        response = ""
        for filename in useful_codes:
            for def_name in useful_codes[filename]:
                response += f"{filename}\n{useful_codes[filename][def_name]['description']}\n\n"
                response += "```\n"
                response += useful_codes[filename][def_name]["code"]
                response += "\n```\n\n"
        response = response.strip()

        with open(self.code_snippet_filename, 'w',
                  encoding="utf8") as code_snippet_file:
            code_snippet_file.write(response)

        self.logger.info("Relevant code snippets written to file")

    def kill(self):
        """
        Kill the Aider agent process.
        """
        self.logger.info("Killing process")
        self._process.kill()
