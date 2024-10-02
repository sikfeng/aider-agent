import json
from pathlib import Path
import websockets

from raider_backend import utils
from raider_backend.handlers.base_handler import BaseHandler
from raider_backend.connection_managers.base_connection_manager import BaseConnectionManager


class InitAgentManagerError(RuntimeError):
    pass

class AgentManagerHandler(BaseHandler):
    def __init__(self):
        super().__init__()

    def initialize_agent(self, repo_dir: str, timeout: int):
        # Initializes AgentManager with MainRepoAgent at repo_dir
        repo_dir = utils.get_absolute_path(repo_dir)
        if not Path(repo_dir).exists():
            error_msg = f"Failed to initialize AgentManager on {repo_dir}. Directory does not exist."
            self.logger.error(error_msg)
            raise InitAgentManagerError(error_msg)
        command = f"init_agent_manager --main-repo-dir {repo_dir} --port {{port}}"
        process, port = self._init_process(repo_dir, command, directory=repo_dir, timeout=timeout)
        if process and port:
            self.agents[repo_dir] = {
                'process': process,
                'port': port,
                'repo_dir': repo_dir
            }
            self.logger.info("Agent %s initialized", repo_dir)
        else:
            error_msg = f"Failed to initialize AgentManager on {repo_dir}. Timeout exceeded."
            self.logger.error(error_msg)
            raise InitAgentManagerError(error_msg)

    async def handle_message(self, main_repo_dir: str, session_id: str, method: str, params: dict): 
        main_repo_dir = utils.get_absolute_path(main_repo_dir)

        if method == "init_agent_manager":
            if main_repo_dir in self.agents:
                self.logger.info("Agent %s already initialized", main_repo_dir)
                yield {"error": f"AgentManager on {main_repo_dir} already initialized"}
                return
            timeout = params.get("timeout", 10)
            self.initialize_agent(main_repo_dir, timeout)
            return

        if main_repo_dir not in self.agents:
            self.logger.info("Agent %s not yet initialized", main_repo_dir)
            yield {"error": f"AgentManager on {main_repo_dir} not initialized yet"}
            return

        port = self.agents[main_repo_dir]['port']
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
                    break

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
