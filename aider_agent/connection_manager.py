"""
Manages WebSocket connections and message buffering.

This class handles the lifecycle of WebSocket connections, including
accepting new connections, disconnecting clients, sending messages,
buffering messages for disconnected clients, and sending keepalive
pings at regular intervals.
"""
import asyncio
import logging
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("ConnectionManager")


class ConnectionManager:
    """
    Manages WebSocket connections and message buffering.
    """

    def __init__(self):
        """
        Initializes the ConnectionManager with empty lists for active
        connections and message buffer.
        """
        self.active_connections = []
        self.message_buffer = []

    async def connect(self, websocket: WebSocket):
        """
        Accepts a new WebSocket connection and adds it to the list of
        active connections.

        :param websocket: The WebSocket connection to accept.
        """
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket connection accepted")

    def disconnect(self, websocket: WebSocket):
        """
        Removes a WebSocket connection from the list of active
        connections.

        :param websocket: The WebSocket connection to remove.
        """
        self.active_connections.remove(websocket)
        logger.info("Client disconnected")

    async def send_message(self, websocket: WebSocket, message: dict):
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
            self.message_buffer.append(message)
            logger.warning("Message buffered due to disconnection")

    async def send_buffered_messages(self, websocket: WebSocket):
        """
        Sends all buffered messages to a specific WebSocket connection.

        :param websocket: The WebSocket connection to send the buffered
            messages to.
        """
        while self.message_buffer:
            buffered_message = self.message_buffer.pop(0)
            await self.send_message(websocket, buffered_message)
            logger.info("Sent buffered message: %s", buffered_message)

    async def send_keepalive_pings(self, websocket: WebSocket):
        """
        Sends keepalive pings to a specific WebSocket connection at regular
        intervals.

        :param websocket: The WebSocket connection to send the
            keepalive pings to.
        """
        while True:
            await asyncio.sleep(10)  # Adjust the interval as needed
            await self.send_message(websocket, {"ping": "keepalive"})
            logger.debug("Sent keepalive ping")
