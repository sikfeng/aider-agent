from typing import Any, Dict

from fastapi import WebSocket

from raider_backend.handlers.agent_manager_handler import AgentManagerHandler
from raider_backend.connection_managers.base_connection_manager import BaseConnectionManager

class LaunchConnectionManager(BaseConnectionManager):
    def __init__(self) -> None:
        super().__init__()
        self.agent_manager_handler: AgentManagerHandler = AgentManagerHandler()

    async def _on_receive(self, websocket: WebSocket,
                          session_id: str, data: Dict[str, Any]) -> None:
        """
        Processes incoming messages and performs the corresponding
        actions based on the method specified in the message.

        :param websocket: The WebSocket connection from which the
            message was received.
        :param session_id: The session identifier for the connection.
        :param data: The data received from the WebSocket connection.
            The expected format of the `data` parameter is a dictionary
            with at least three keys: `main_repo_dir`, `method` and `params`.
        """
        main_repo_dir = data.get("main_repo_dir")
        method = data.get("method")
        params = data.get("params", {})

        response = await self.agent_manager_handler.handle_message(
            session_id=session_id, main_repo_dir=main_repo_dir, method=method, params=params)
        response = {"result": response}
        await self.send_message(websocket, response, session_id)
        await self.send_message(websocket, BaseConnectionManager.END_OF_MESSAGE_RESPONSE, session_id)