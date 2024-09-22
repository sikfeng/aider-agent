import logging
import json
from pathlib import Path
import subprocess
import time
from typing import Dict
import websockets

import httpx

from raider_backend import utils
from .base_handler import BaseHandler


class InitAgentManagerError(RuntimeError):
    pass

class AgentManagerHandler(BaseHandler):
    def __init__(self):
        super().__init__()

    def initialize_agent(self, repo_dir: str):
        repo_dir = utils.get_absolute_path(repo_dir)
        command = f"init_agent_manager --main-repo-dir {repo_dir} --port {{port}}"
        process, port = self._init_process(repo_dir, command)
        if process and port:
            self.agents[repo_dir] = {
                'process': process,
                'port': port,
                'repo_dir': repo_dir
            }
            self.logger.info("Agent %s initialized", repo_dir)
        else:
            raise InitAgentManagerError(f"Failed to initialize AgentManager on {repo_dir}.")

    async def handle_message(self, main_repo_dir: str, session_id: str, method: str, params: dict): 
        main_repo_dir = utils.get_absolute_path(main_repo_dir)
        if main_repo_dir not in self.agents:
            self.logger.info("Agent %s not yet initialized", main_repo_dir)
            self.initialize_agent(main_repo_dir)

        port = self.agents[main_repo_dir]['port']
        async with websockets.connect(f"ws://localhost:{port}/ws/{session_id}", ping_interval=None) as websocket:
            request = {
                "method": method,
                "params": params or {}
            }
            await websocket.send(json.dumps(request))
            response_data = ""
            while True:
                response = await websocket.recv()
                partial_response_data = json.loads(response)
                if "ping" in partial_response_data:
                    continue  # Ignore keepalive pings
                if partial_response_data == {
                        "<END_OF_MESSAGE>": "<END_OF_MESSAGE>"}: # TODO: check if equal to value in ConnectionManager
                    return response_data
                response_data += partial_response_data["result"]
                self.logger.info(partial_response_data["result"])
