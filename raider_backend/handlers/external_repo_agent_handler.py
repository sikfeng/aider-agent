import asyncio
import json
from pathlib import Path
from typing import AsyncGenerator
import websockets

from raider_backend import utils
from raider_backend import parse
from raider_backend.prompts import ExternalRepoAgentHandlerPrompts
from raider_backend.handlers.base_handler import BaseHandler
from raider_backend.connection_managers.base_connection_manager import BaseConnectionManager


class InitExternalRepoAgentError(RuntimeError):
    pass


class ExternalRepoAgentHandler(BaseHandler):
    def __init__(self):
        super().__init__()
        self.disabled_agents: set = set()

    def disable_agent(self, repo_dir: str) -> None:
        """
        Disable an agent for a specific repo directory.

        :param repo_dir: The directory of the repository to disable.
        """
        self.disabled_agents.add(repo_dir)

    def is_agent_disabled(self, repo_dir: str) -> bool:
        """
        Check if an agent for a specific repo directory is disabled.

        :param repo_dir: The directory of the repository to check.
        :return: True if the agent is disabled, False otherwise.
        """
        return repo_dir in self.disabled_agents

    def enable_agent(self, repo_dir: str) -> None:
        """
        Enable a previously disabled agent for a specific repo directory.

        :param repo_dir: The directory of the repository to enable.
        """
        repo_dir = utils.get_absolute_path(repo_dir)
        if repo_dir in self.disabled_agents:
            self.disabled_agents.remove(repo_dir)
            self.logger.info(f"Enabled external repo agent for {repo_dir}")
        else:
            self.logger.info(f"Agent for {repo_dir} was not disabled")

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

    def initialize_agent(self, agent_id: str, repo_dir: str, model_name: str = "azure/gpt-4o", timeout: int = 10):
        repo_dir = utils.get_absolute_path(repo_dir)
        command = f"init_ext_repo_agent --port {{port}} --model-name {model_name}"
        process, port = self._init_process(agent_id, command, directory=repo_dir, timeout=timeout)
        if process and port:
            self.agents[agent_id] = {
                'process': process,
                'port': port,
                'repo_dir': repo_dir,
                'model_name': model_name
            }
        else:
            raise InitExternalRepoAgentError(f"Failed to initialize ExternalRepoAgent for {agent_id} on {repo_dir}.")

    async def handle_message(self, agent_id: str, session_id: str, method: str, params: dict):
        if agent_id not in self.agents:
            self.logger.warning("Agent %s not yet initialized", agent_id)
            yield {"warning": "Agent not initialized yey"}
            return

        port = self.agents[agent_id]['port']
        async with websockets.connect(f"ws://localhost:{port}/ws/{session_id}", ping_interval=None) as websocket:
            request = {
                "method": method,
                "params": params or {}
            }
            await websocket.send(json.dumps(request))
            while True:
                response = await websocket.recv()
                partial_response_data = json.loads(response)
                if partial_response_data == BaseConnectionManager.KEEP_ALIVE_PING:
                    continue  # Ignore keepalive pings
                elif partial_response_data == BaseConnectionManager.END_OF_MESSAGE_RESPONSE:
                    return

                if "info" in partial_response_data:
                    self.logger.info(partial_response_data["info"])
                    yield partial_response_data
                elif "warning" in partial_response_data:
                    self.logger.warning(partial_response_data["warning"])
                    yield partial_response_data
                elif "error" in partial_response_data:
                    self.logger.error(partial_response_data["error"])
                    yield partial_response_data
                elif "result" in partial_response_data:
                    self.logger.info(partial_response_data["result"])
                    yield partial_response_data

    async def run(self, agent_id: str, msg: str):
        raise RuntimeError("ExternalRepoAgent should NOT run any tasks!")

    async def run_stream(self, agent_id: str, msg: str):
        raise RuntimeError("ExternalRepoAgent should NOT run any tasks!")

    async def ask(self, agent_id: str, msg: str) -> AsyncGenerator[str, None]:
        async for partial_response in self.handle_message(agent_id, "session", "ask", {"msg": msg}):
            yield partial_response

    async def get_repo_map(self, agent_id: str, session_id: str) -> AsyncGenerator[str, None]:
        async for partial_response in self.handle_message(agent_id, session_id, "get_repo_map", {}):
            yield partial_response

    # TODO: needs cleaning up
    async def find_relevant_code(self, agent_id: str, task: str, session_id: str):
        repo_dir = self.agents[agent_id]['repo_dir']
        model_name = self.agents[agent_id]['model_name']
        code_snippet_filename = utils.get_absolute_path(
            f"code_snippets_{agent_id.replace('/', '').replace('.','')}.txt")

        self.logger.info(f"Finding relevant code for agent {agent_id}, task: {task}")

        # Delete existing code snippet file if it exists
        Path(code_snippet_filename).unlink(missing_ok=True)

        # Step 1: Get list of relevant files
        async for response in self.get_repo_map(agent_id, session_id):
            # repomap should be a single response
            repo_map = response


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
