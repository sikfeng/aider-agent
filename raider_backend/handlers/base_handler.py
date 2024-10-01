from abc import ABC, abstractmethod
import logging
import subprocess
import time
import socket
from typing import Dict
import httpx

class BaseHandler(ABC):
    def __init__(self):
        self.agents: Dict[str, Dict] = {}
        self.logger = logging.getLogger(self.__class__.__name__)

    @staticmethod
    def get_free_port():
        sock = socket.socket()
        sock.bind(('', 0))
        port = sock.getsockname()[1]
        sock.close()
        return port

    def wait_for_ping(self, port: int, timeout: int = 10) -> bool:
        self.logger.info(f"Waiting for ping response on port {port}.")
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = httpx.get(f"http://localhost:{port}/ping")
                if response.json() == "pong":
                    self.logger.info(f"Ping successful on port {port}.")
                    return True
            except httpx.RequestError as e:
                self.logger.debug(f"Ping request failed on port {port}: {e}")
            time.sleep(1)  # Wait for 1 second before retrying
        self.logger.warning(f"Ping timeout reached for port {port}.")
        return False

    @abstractmethod
    def initialize_agent(self, agent_id: str, **kwargs):
        pass

    def _init_process(self, agent_id: str, command: str, max_retries: int = 5, directory: str = ".", timeout: int = 10):
        for _ in range(max_retries):
            port = self.get_free_port()
            self.logger.info(f"Attempting to start process for agent {agent_id} on port {port}")
            process = subprocess.Popen(
                command.format(port=port),
                shell=True,
                cwd=directory,
            )
            if self.wait_for_ping(port, timeout=timeout):
                self.logger.info(f"Process for agent {agent_id} on port {port} successfully initialized.")
                return process, port
            if process.poll() is None:
                process.kill()
            self.logger.warning(f"Attempt to start process for agent {agent_id} on port {port} failed.")
        self.logger.error(f"Process for agent {agent_id} failed to initialize within {max_retries} tries.")
        return None, None

    def kill_agent(self, agent_id: str):
        if agent_id in self.agents:
            process: subprocess.Popen = self.agents[agent_id].get('process')
            if process and process.poll() is None:
                self.logger.info(f"Killing process for agent {agent_id}")
                process.kill()
            self.agents.pop(agent_id)

    def kill_all_agents(self):
        for agent_id in list(self.agents.keys()):
            self.kill_agent(agent_id)
