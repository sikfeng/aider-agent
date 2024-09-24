import json
import websockets

from raider_backend import utils
from raider_backend.handlers.base_handler import BaseHandler
from raider_backend.connection_managers.base_connection_manager import BaseConnectionManager


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
                if partial_response_data == BaseConnectionManager.KEEP_ALIVE_PING:
                    continue  # Ignore keepalive pings
                elif partial_response_data == BaseConnectionManager.END_OF_MESSAGE_RESPONSE:
                    return response_data

                if "error" in partial_response_data:
                    response_data += partial_response_data["error"]
                    self.logger.error(partial_response_data["error"])
                elif "result" in partial_response_data:
                    response_data += partial_response_data["result"]
                    self.logger.info(partial_response_data["result"])
