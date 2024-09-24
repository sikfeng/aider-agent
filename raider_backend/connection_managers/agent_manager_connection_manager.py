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
            repo_dir = params.get("repo_dir")
            model_name = params.get("model_name", "azure/gpt-4o")
            timeout = params.get("timeout", 10)
            result = agent_manager.init_external_repo_agent(
                repo_dir, model_name, timeout)
            response = {"result": "Success" if result else "Failure"}
            await self.send_message(websocket, response, session_id)

        elif method == "get_external_repo_agents":
            agents = json.dumps(agent_manager.get_external_repo_agents())
            response = {"result": agents}
            await self.send_message(websocket, response, session_id)

        elif method == "generate_subtasks":
            objective = params.get("objective")
            async for response in agent_manager.generate_subtasks(objective):
                self.logger.info("Response: %s", response)
                await self.send_message(websocket, response, session_id)

        elif method == "run_subtask":
            subtask = params.get("subtask")
            async for response in agent_manager.run_subtask(subtask):
                await self.send_message(websocket, {"result": response}, session_id)

        elif method == "undo":
            agent_manager.undo()
            await self.send_message(websocket, {"result": "Undo completed"}, session_id)

        elif method == "shutdown":
            result = agent_manager.shutdown()
            await self.send_message(websocket, {"result": result}, session_id)
            self.agent_managers.pop(session_id)

        else:
            await self.send_message(websocket, {"error": f"Unknown method: {method}"}, session_id)

        self.logger.info("End of message.")
        await self.send_message(websocket, BaseConnectionManager.END_OF_MESSAGE_RESPONSE, session_id)
