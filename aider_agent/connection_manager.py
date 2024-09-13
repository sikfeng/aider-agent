import asyncio
import logging
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("ConnectionManager")


class ConnectionManager:
    def __init__(self):
        self.active_connections = []
        self.message_buffer = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket connection accepted")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.warning("Client disconnected")

    async def send_message(self, websocket: WebSocket, message: dict):
        try:
            await websocket.send_json(message)
        except WebSocketDisconnect:
            self.message_buffer.append(message)
            logger.warning("Message buffered due to disconnection")

    async def send_buffered_messages(self, websocket: WebSocket):
        while self.message_buffer:
            buffered_message = self.message_buffer.pop(0)
            await self.send_message(websocket, buffered_message)
            logger.info(f"Sent buffered message: {buffered_message}")

    async def send_keepalive_pings(self, websocket: WebSocket):
        while True:
            await asyncio.sleep(10)  # Adjust the interval as needed
            await self.send_message(websocket, {"ping": "keepalive"})
            logger.debug("Sent keepalive ping")
