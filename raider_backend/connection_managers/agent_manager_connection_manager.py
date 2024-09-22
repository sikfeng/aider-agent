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
            subtasks = json.dumps(await agent_manager.generate_subtasks(objective))
            response = {"result": subtasks}
            await self.send_message(websocket, response, session_id)

        elif method == "run_subtask":
            subtask = params.get("subtask")
            async for response in agent_manager.run_subtask(subtask):
                await self.send_message(websocket, {"result": response}, session_id)

        elif method == "run_multiple_subtasks":
            subtasks = params.get("subtasks")
            async for response in agent_manager.run_multiple_subtasks(subtasks):
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

        await self.send_message(websocket, self.END_OF_MESSAGE_RESPONSE, session_id)
