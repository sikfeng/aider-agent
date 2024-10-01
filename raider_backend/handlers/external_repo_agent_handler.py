import json
from pathlib import Path
from typing import AsyncGenerator, Dict
import websockets

from raider_backend import utils
from raider_backend.handlers.base_handler import BaseHandler
from raider_backend.connection_managers.base_connection_manager import BaseConnectionManager
from raider_backend.code_rag import CodeRAG


class InitExternalRepoAgentError(RuntimeError):
    pass


class ExternalRepoAgentHandler(BaseHandler):
    def __init__(self):
        super().__init__()
        self.code_rags: Dict[str, CodeRAG] = {}

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
        command = f"exec init_ext_repo_agent --port {{port}} --model-name {model_name}"
        process, port = self._init_process(agent_id, command, directory=repo_dir, timeout=timeout)
        if process and port:
            self.agents[agent_id] = {
                'process': process,
                'port': port,
                'repo_dir': repo_dir,
                'model_name': model_name
            }
            self.code_rags[agent_id] = CodeRAG(repo_dir, ["js", "jsx", "ts", "tsx", "py"])
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
        code_rag = self.code_rags[agent_id]
        code_snippet_filename = utils.get_absolute_path(
            f"code_snippets_{agent_id.replace('/', '').replace('.','')}.txt")

        self.logger.info(f"Finding relevant code for agent {agent_id}, task: {task}")

        # Delete existing code snippet file if it exists
        Path(code_snippet_filename).unlink(missing_ok=True)

        '''
        system_prompt = """
You are a software engineer. You are given a task and a codebase.
Your job is to find the code that is relevant to the task.
"""
        user_prompt = """
Give me keywords that describe the functionality you need to implement.

e.g. auto-complete, webview, SSO, etc.
"""
        keywords = await utils.strict_json_async_retry(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_format={
                "keywords": "Array of keywords describing the functionality needed, type: Array[str]",
            },
            llm=utils.llm_async(model_name)
        )
        self.logger.info("Task: %s", task)
        self.logger.info("Keywords generated: %s", keywords)

        useful_codes = []

        for keyword in keywords:
            useful_codes += code_rag.retrieve(keyword)
        '''
        useful_codes = code_rag.retrieve(task)
        response = "\n\n--------------\n\n".join(["```\n" + code + "\n```" for code in useful_codes])

        with open(code_snippet_filename, 'w', encoding="utf8") as code_snippet_file:
            code_snippet_file.write(response)

        self.logger.info(f"Relevant code snippets written to file for agent {agent_id}")
