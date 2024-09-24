from abc import ABC, abstractmethod
import asyncio
import logging
from typing import Any, Dict, List

from fastapi import WebSocket, WebSocketDisconnect


class BaseConnectionManager(ABC):
    """
    Manages WebSocket connections and message buffering.
    """
    END_OF_MESSAGE_RESPONSE = {"<END_OF_MESSAGE>": ""}
    KEEP_ALIVE_PING = {"<PING>": ""}

    def __init__(self) -> None:
        """
        Initializes the ConnectionManager with empty lists for active
        connections and message buffer.
        """
        self.active_connections: List[WebSocket] = []
        self.message_buffer: Dict[str, List[Dict[str, Any]]] = {}
        self.logger = logging.getLogger(self.__class__.__name__)

    async def _on_connect(self, websocket: WebSocket, session_id: str) -> None:
        """
        Accepts a new WebSocket connection and adds it to the list of
        active connections.

        :param websocket: The WebSocket connection to accept.
        """
        await websocket.accept()
        self.active_connections.append(websocket)
        self.logger.info("WebSocket connection accepted")

    async def _on_disconnect(self, websocket: WebSocket) -> None:
        """
        Removes a WebSocket connection from the list of active
        connections.

        :param websocket: The WebSocket connection to remove.
        """
        self.active_connections.remove(websocket)
        self.logger.info("Client disconnected")

    @abstractmethod
    async def _on_receive(self, websocket: WebSocket,
                          session_id: str, data: Dict[str, Any]) -> None:
        pass

    async def send_message(self, websocket: WebSocket,
                           message: Dict[str, Any], session_id: str) -> None:
        """
        Sends a message to a specific WebSocket connection. If the
        connection is disconnected, the message is buffered.

        :param websocket: The WebSocket connection to send the message
            to.
        :param message: The message to send.
        """
        try:
            await websocket.send_json(message)
        except WebSocketDisconnect:
            self.message_buffer[session_id].append(message)
            self.logger.warning("Message buffered due to disconnection")

    async def send_buffered_messages(
            self,
            websocket: WebSocket,
            session_id: str) -> None:
        """
        Sends all buffered messages to a specific WebSocket connection.

        :param websocket: The WebSocket connection to send the buffered
            messages to.
        """
        if session_id not in self.message_buffer:
            return

        while self.message_buffer[session_id]:
            buffered_message = self.message_buffer[session_id].pop(0)
            await self.send_message(websocket, buffered_message, session_id)
            self.logger.info("Sent buffered message: %s", buffered_message)

    async def send_keepalive_pings(
            self,
            websocket: WebSocket,
            session_id: str) -> None:
        """
        Sends keepalive pings to a specific WebSocket connection at
        regular intervals.

        :param websocket: The WebSocket connection to send the
            keepalive pings to.
        """
        while True:
            await asyncio.sleep(10)  # Adjust the interval as needed
            await self.send_message(websocket, BaseConnectionManager.KEEP_ALIVE_PING, session_id)
            self.logger.debug("Sent keepalive ping")

    async def websocket_endpoint(
            self,
            websocket: WebSocket,
            session_id: str) -> None:
        """
        WebSocket endpoint to handle various agent management tasks.

        This endpoint manages WebSocket connections and processes
        incoming messages to perform tasks such as initializing
        external repo agents, generating and fine-tuning subtasks,
        running subtasks, and shutting down the agent manager.

        :param websocket: The WebSocket connection instance.
        :param session_id: The session identifier for the connection.

        :raises WebSocketDisconnect: If the WebSocket connection is
            disconnected.
        """
        await self._on_connect(websocket, session_id)
        keepalive_task = asyncio.create_task(
            self.send_keepalive_pings(websocket, session_id))

        try:
            await self.send_buffered_messages(websocket, session_id)

            while True:
                data = await websocket.receive_json()
                self.logger.info("Received data: %s", data)
                await self._on_receive(websocket, session_id, data)

        except WebSocketDisconnect:
            await self._on_disconnect(websocket)
        finally:
            keepalive_task.cancel()
            self.logger.info("Keepalive task cancelled")

    def ping(self) -> str:
        result = "pong"
        return result