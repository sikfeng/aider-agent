from typing import Any, Dict, TYPE_CHECKING

from fastapi import WebSocket

from raider_backend.connection_managers.base_connection_manager import BaseConnectionManager

if TYPE_CHECKING:
    from raider_backend.repo_agents.external_repo_agent import ExternalRepoAgent

class RepoAgentConnectionManager(BaseConnectionManager):
    def __init__(self) -> None:
        super().__init__()
        self.repo_agents: Dict[str, ExternalRepoAgent] = {}

    async def _on_connect(self, websocket: WebSocket, session_id: str) -> None:
        await super()._on_connect(websocket, session_id)
        if self.repo_agents.get(session_id) is None:
            from raider_backend.repo_agents.external_repo_agent import ExternalRepoAgent
            self.repo_agents[session_id] = ExternalRepoAgent()
            self.logger.info(
                "Initialized ExternalRepoAgent with session ID %s", session_id)

    async def _on_receive(self, websocket: WebSocket, session_id: str, data: Dict[str, Any]) -> None:
        method = data.get("method")
        params = data.get("params", {})

        repo_agent = self.repo_agents[session_id]

        if method == "run":
            result = repo_agent.run(**params)
            response = {"result": result}
            await self.send_message(websocket, response, session_id)
        elif method == "run_stream":
            async for partial_response in repo_agent.run_stream(**params):
                await self.send_message(websocket, partial_response, session_id)
        elif method == "ask":
            async for partial_response in repo_agent.ask(**params):
                await self.send_message(websocket, {"result": partial_response}, session_id)
        elif method == "get_repo_map":
            result = repo_agent.get_repo_map()
            response = {"result": result}
            await self.send_message(websocket, response, session_id)
        elif method == "ping":
            response = {"result": "pong"}
            await self.send_message(websocket, response, session_id)
        else:
            await self.send_message(websocket, {"error": f"Unknown method: {method}"}, session_id)

        await self.send_message(websocket, self.END_OF_MESSAGE_RESPONSE, session_id)