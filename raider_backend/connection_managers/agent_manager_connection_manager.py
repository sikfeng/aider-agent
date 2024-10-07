import json
from typing import Any, Dict

from fastapi import WebSocket

from raider_backend.agent_manager import AgentManager
from raider_backend.connection_managers.base_connection_manager import BaseConnectionManager

class AgentManagerConnectionManager(BaseConnectionManager):
    def __init__(self) -> None:
        super().__init__()
        self.agent_managers: Dict[str, AgentManager] = {}

    async def _on_connect(self, websocket: WebSocket, session_id: str) -> None:
        await super()._on_connect(websocket, session_id)
        if self.agent_managers.get(session_id) is None:
            self.agent_managers[session_id] = AgentManager()
            self.logger.info(
                "Initialized AgentManager with session ID %s", session_id)

    async def _on_receive(self, websocket: WebSocket, session_id: str, data: Dict[str, Any]) -> None:
        method = data.get("method")
        params = data.get("params", {})

        agent_manager = self.agent_managers[session_id]

        # TODO: need to standardize the AgentManager methods to yield data, 
        # and for the methods to format them as info, warning, error, or results
        # TODO: create classes for each packet to standardize the format

        if method == "init_external_repo_agent":
            result = agent_manager.init_external_repo_agent(**params)
            response = {"result": "Success" if result else "Failure"}
            await self.send_message(websocket, response, session_id)

        elif method == "get_external_repo_agents":
            agents = agent_manager.get_external_repo_agents()
            response = {"result": agents}
            await self.send_message(websocket, response, session_id)

        elif method == "ask_repo":
            async for response in agent_manager.ask_repo(**params):
                self.logger.info("Response: %s", response)
                await self.send_message(websocket, response, session_id)

        elif method == "generate_subtasks":
            async for response in agent_manager.generate_subtasks(**params):
                self.logger.info("Response: %s", response)
                await self.send_message(websocket, response, session_id)

        elif method == "run_subtask":
            async for response in agent_manager.run_subtask(session_id=session_id, **params):
                await self.send_message(websocket, response, session_id)
        
        elif method == "generate_commands":
            async for response in agent_manager.generate_commands(**params):
                await self.send_message(websocket, response, session_id)

        elif method == "undo":
            response = agent_manager.undo()
            await self.send_message(websocket, response, session_id)

        elif method == "shutdown":
            response = agent_manager.shutdown()
            await self.send_message(websocket, response, session_id)
            self.agent_managers.pop(session_id)

        elif method == "disable_external_repo_agent":
            agent_id = params.get("agent_id")
            if agent_id:
                result = agent_manager.disable_external_repo_agent(agent_id)
                response = {"result": "Success" if result else "Failure"}
            else:
                response = {"error": "Missing agent_id parameter"}
            await self.send_message(websocket, response, session_id)

        elif method == "enable_external_repo_agent":
            agent_id = params.get("agent_id")
            if agent_id:
                result = agent_manager.enable_external_repo_agent(agent_id)
                response = {"result": "Success" if result.get("result") == "Success" else "Failure"}
            else:
                response = {"error": "Missing agent_id parameter"}
            await self.send_message(websocket, response, session_id)

        else:
            await self.send_message(websocket, {"error": f"Unknown method: {method}"}, session_id)

        self.logger.info("End of message.")
        await self.send_message(websocket, BaseConnectionManager.END_OF_MESSAGE_RESPONSE, session_id)
