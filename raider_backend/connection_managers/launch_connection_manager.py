from typing import Any, Dict
import json
from fastapi import WebSocket

from raider_backend.handlers.agent_manager_handler import AgentManagerHandler, InitAgentManagerError
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
        
        method = data.get("method")
        params = data.get("params", {})
        main_repo_dir = data.get("main_repo_dir")
        
        if method == "query":
            try:
                import web_raider
            except ModuleNotFoundError as e:
                self.logger.error("Web Raider package not found")
                raise e
            
            response = [
                dict(
                    type=item.get("type", "").lower(),
                    name=item.get("name", ""),
                    url=item.get("url", "")
                ) for item in json.loads(web_raider.pipeline_main(**params))
            ]
            await self.send_message(websocket, {"result": response}, session_id)
        
        else:
            try:
                async for response in self.agent_manager_handler.handle_message(
                    session_id=session_id, main_repo_dir=main_repo_dir, method=method, params=params):
                    await self.send_message(websocket, response, session_id)
            except InitAgentManagerError as e:
                await self.send_message(websocket, {"error": str(e)}, session_id)
        
        await self.send_message(websocket, BaseConnectionManager.END_OF_MESSAGE_RESPONSE, session_id)