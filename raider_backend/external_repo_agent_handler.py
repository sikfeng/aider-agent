import asyncio
from pathlib import Path
from typing import AsyncGenerator

import httpx

from . import utils
from . import parse
from .prompts import ExternalRepoAgentHandlerPrompts
from .base_handler import BaseHandler


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


class ExternalRepoAgentHandler(BaseHandler):
    def __init__(self):
        super().__init__()

    def _get_agent_port(self, agent_id: str) -> int:
        if agent_id not in self.agents:
            raise ValueError(f"Agent {agent_id} not initialized")
        return self.agents[agent_id]['port']

    def _get_agent_repo_dir(self, agent_id: str) -> str:
        if agent_id not in self.agents:
            raise ValueError(f"Agent {agent_id} not initialized")
        return self.agents[agent_id]['repo_dir']

    def _get_agent_model_name(self, agent_id: str) -> str:
        if agent_id not in self.agents:
            raise ValueError(f"Agent {agent_id} not initialized")
        return self.agents[agent_id]['model_name']

    def initialize_agent(self, agent_id: str, repo_dir: str, model_name: str = "azure/gpt-4o"):
        repo_dir = utils.get_absolute_path(repo_dir)
        command = f"exec init_repo_agent --port {{port}} --model-name {model_name}"
        process, port = self._init_process(agent_id, command)
        if process and port:
            self.agents[agent_id] = {
                'process': process,
                'port': port,
                'repo_dir': repo_dir,
                'model_name': model_name
            }
        else:
            raise InitExternalRepoAgentError(f"Failed to initialize ExternalRepoAgent for {agent_id} on {repo_dir}.")

    def run(self, agent_id: str, msg: str) -> str:
        if agent_id not in self.agents:
            raise ValueError(f"Agent {agent_id} not initialized")

        port = self.agents[agent_id]['port']
        self.logger.info(f"Sending message to agent {agent_id}: {msg}")
        response = httpx.post(
            f"http://0.0.0.0:{port}/run",
            params={"msg": msg},
        )
        result = response.json()["result"]
        self.logger.debug(f"Received response from agent {agent_id}: {result}")
        return result

    async def run_stream(self, agent_id: str, msg: str, chunk_size: int = 64) -> AsyncGenerator[str, None]:
        port = self._get_agent_port(agent_id)
        self.logger.info(f"Sending message for streaming to agent {agent_id}: {msg}")
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"http://0.0.0.0:{port}/run_stream",
                params={"msg": msg}
            ) as response:
                async for chunk in response.aiter_text(chunk_size=chunk_size):
                    self.logger.debug(f"Received partial response from agent {agent_id}: {chunk}")
                    yield chunk

    async def ask(self, agent_id: str, msg: str, chunk_size: int = 64) -> AsyncGenerator[str, None]:
        port = self._get_agent_port(agent_id)
        self.logger.info(f"Asking question to agent {agent_id}: {msg}")
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"http://0.0.0.0:{port}/ask",
                params={"msg": msg}
            ) as response:
                async for chunk in response.aiter_text(chunk_size=chunk_size):
                    self.logger.debug(f"Received partial response from agent {agent_id}: {chunk}")
                    yield chunk

    # TODO
    def run_cmd(self, agent_id: str, cmd: str) -> str:
        port = self._get_agent_port(agent_id)
        self.logger.info(f"Running command for agent {agent_id}: {cmd}")
        response = httpx.post(
            f"http://0.0.0.0:{port}/msg",
            params={"msg": f"/run {cmd}"},
        )
        result = response.json()["result"]
        self.logger.info(f"Received command response from agent {agent_id}: {result}")
        return result

    def get_repo_map(self, agent_id: str) -> str:
        port = self._get_agent_port(agent_id)
        self.logger.info(f"Getting repository map for agent {agent_id}")
        response = httpx.get(
            f"http://0.0.0.0:{port}/get_repo_map"
        )
        repo_map = response.json()
        self.logger.debug(f"Received repository map for agent {agent_id}: {repo_map}")
        return repo_map

    async def find_relevant_code(self, agent_id: str, task: str):
        repo_dir = self._get_agent_repo_dir(agent_id)
        model_name = self._get_agent_model_name(agent_id)
        code_snippet_filename = utils.get_absolute_path(
            f"code_snippets_{repo_dir.replace('/', '').replace('.','')}.txt")

        self.logger.info(f"Finding relevant code for agent {agent_id}, task: {task}")

        # Delete existing code snippet file if it exists
        Path(code_snippet_filename).unlink(missing_ok=True)

        # Step 1: Get list of relevant files
        repo_map = self.get_repo_map(agent_id)

        system_prompt = ExternalRepoAgentHandlerPrompts.SYSTEM_PROMPT_FIND_RELEVANT_FILENAMES.format(
            repo_map=repo_map)
        user_prompt = ExternalRepoAgentHandlerPrompts.USER_PROMPT_FIND_RELEVANT_FILENAMES.format(
            task=task)

        self.logger.debug(f"Sending prompts to LLM to find relevant filenames for agent {agent_id}")
        res = await utils.strict_json_retry(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_format={
                'filenames': "Array of filenames which contain relevant for completing the user's task, type: Array[str]"
            },
            llm=utils.llm(model_name)
        )

        # Ensure that the filenames were not hallucinated
        filenames = [filename for filename in res["filenames"]
                     if (Path(repo_dir) / filename).is_file()]
        if len(filenames) == 0:
            self.logger.info(f"No relevant filenames found for agent {agent_id}")
            return

        # Step 2: Get the relevant definitions
        self.logger.debug(f"Getting relevant definitions from filenames for agent {agent_id}")
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
            llm=utils.llm(model_name)
        )

        useful_defs = {filename: res[filename]
                       for filename in res if len(res[filename]) > 0}
        if len(useful_defs) == 0:
            self.logger.info(f"No useful definitions found for agent {agent_id}")
            return

        # Step 3: Get the code snippets that were requested, and do
        # one more round of checking if they are actually relevant
        semaphore = asyncio.Semaphore(self.agents[agent_id].get('max_concurrent_llm_queries', 1))

        async def process_file(filename, semaphore):
            self.logger.info(f"Processing file for agent {agent_id}: {filename}")

            class_defs, method_defs, function_defs = parse.get_class_method_function_defs(
                Path(repo_dir) / filename)
            if class_defs is None and method_defs is None and function_defs is None:
                self.logger.debug(f"No definitions parsed from file for agent {agent_id}: {filename}")
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
                    self.logger.debug(f"Definition {def_name} not found in file for agent {agent_id}: {filename}")

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

                self.logger.debug(f"Sending prompts to LLM for agent {agent_id}, file: {filename}")
                response = await utils.strict_json_async_retry(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    output_format={
                        def_name: {
                            "useful": f"whether `{def_name}` is useful, type: bool",
                            "description": f"explanation of why `{def_name}` is useful for the task, type: str"
                        } for def_name in definition_codes
                    },
                    llm=utils.llm_async(model_name)
                )

            result = {def_name: response[def_name]
                      for def_name in response if response[def_name]["useful"]}
            for def_name in result:
                result[def_name]["code"] = definition_codes[def_name]

            self.logger.info(f"Finished processing file for agent {agent_id}: {filename}")
            return result

        self.logger.debug(f"Creating tasks to process files for agent {agent_id}")
        tasks = [process_file(filename, semaphore) for filename in useful_defs]
        results = await asyncio.gather(*tasks)

        useful_codes = {
            filename: result for filename,
            result in zip(
                useful_defs,
                results) if len(result) > 0}

        if not useful_codes:
            self.logger.info(f"No useful code snippets found for agent {agent_id}")
            return

        self.logger.debug(f"Useful codes found for agent {agent_id}: {useful_codes}")

        response = ""
        for filename in useful_codes:
            for def_name in useful_codes[filename]:
                response += f"{filename}\n{useful_codes[filename][def_name]['description']}\n\n"
                response += "```\n"
                response += useful_codes[filename][def_name]["code"]
                response += "\n```\n\n"
        response = response.strip()

        with open(code_snippet_filename, 'w', encoding="utf8") as code_snippet_file:
            code_snippet_file.write(response)

        self.logger.info(f"Relevant code snippets written to file for agent {agent_id}")
