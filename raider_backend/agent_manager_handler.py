import logging
import json
from pathlib import Path
import subprocess
import time
from typing import Dict
import websockets

import httpx

from . import utils


class InitAgentManagerError(RuntimeError):
    pass


class AgentManagerHandler:
    def __init__(self):
        self.agent_manager_subprocesses: Dict[str, subprocess.Popen] = {}
        self.agent_manager_ports: Dict[str, int] = {}

    def init_agent_manager(self,
                           max_init_retry: int = 5,
                           repo_dir: str = ".") -> None:
        if not Path(repo_dir).is_dir():
            self.logger.error(
                ("Attempt to initialize AgentManagerHandler on "
                 "non-existent directory %s."),
                repo_dir)
            raise FileNotFoundError

        # Standardize to use absolute path
        repo_dir = utils.get_absolute_path(repo_dir)
        self.logger = logging.getLogger("AgentManagerHandler")

        def get_free_port():
            import socket
            # TODO: handle potential errors
            sock = socket.socket()
            sock.bind(('', 0))
            port = sock.getsockname()[1]
            sock.close()
            return port

        def wait_for_ping(port) -> bool:
            """
            Wait for the Aider agent to respond with "pong" to a ping
            request.

            :return: True if the agent responds with "pong", False if
                timeout is reached.
            """
            self.logger.info("Waiting for ping response.")
            timeout = 6  # TODO: set as class variable
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    response = httpx.get(f"http://0.0.0.0:{port}/ping")
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

        for _ in range(max_init_retry):
            port = get_free_port()
            subprocess_ = subprocess.Popen(
                (f"init_agent_manager --main-repo-dir {repo_dir} --port {port}"),
                cwd=repo_dir,
                shell=True)
            ping_success = wait_for_ping(port)
            if ping_success:
                self.agent_manager_subprocesses[repo_dir] = subprocess_
                self.agent_manager_ports[repo_dir] = port
                self.logger.info(
                    "AgentManager on port %s returned ping, successfully initialized.", port)
                return

            if subprocess_.poll() is None:
                subprocess_.kill()
            self.logger.warning("AgentManager on port %s killed.", port)
        else:
            # Exhausted retries
            self.logger.error(
                "AgentManager failed to initialize within %s tries, quitting.",
                max_init_retry)
            raise InitAgentManagerError(
                f"Failed to initialize AgentManager on {repo_dir}.")

    async def handle_message(self, session_id, main_repo_dir, method, params):
        main_repo_dir = utils.get_absolute_path(main_repo_dir)
        if main_repo_dir not in self.agent_manager_subprocesses.keys():
            try:
                self.init_agent_manager(repo_dir=main_repo_dir)
            except InitAgentManagerError:
                return f"Failed to initialize AiderManager on {main_repo_dir}"

        port = self.agent_manager_ports[main_repo_dir]
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
                        "<END_OF_MESSAGE>": "<END_OF_MESSAGE>"}:
                    return response_data
                response_data += partial_response_data["result"]
                self.logger.info(partial_response_data["result"])
