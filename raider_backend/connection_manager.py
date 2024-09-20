"""
Manages WebSocket connections and message buffering.

This class handles the lifecycle of WebSocket connections, including
accepting new connections, disconnecting clients, sending messages,
buffering messages for disconnected clients, and sending keepalive
pings at regular intervals.
"""
from abc import ABC, abstractmethod
import asyncio
import json
import logging
import os
import signal
from typing import Any, Dict, List

from fastapi import WebSocket, WebSocketDisconnect

from .agent_manager import AgentManager

logger = logging.getLogger("ConnectionManager")


class ConnectionManager(ABC):
    """
    Manages WebSocket connections and message buffering.
    """
    END_OF_MESSAGE_RESPONSE = {"<END_OF_MESSAGE>": "<END_OF_MESSAGE>"}

    def __init__(self) -> None:
        """
        Initializes the ConnectionManager with empty lists for active
        connections and message buffer.
        """
        self.active_connections: List[WebSocket] = []
        self.message_buffer: Dict[str, List[Dict[str, Any]]] = {}

    async def _on_connect(self, websocket: WebSocket, session_id: str) -> None:
        """
        Accepts a new WebSocket connection and adds it to the list of
        active connections.

        :param websocket: The WebSocket connection to accept.
        """
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket connection accepted")

        if self.agent_managers.get(session_id) is None:
            self.agent_managers[session_id] = AgentManager()

    async def _on_disconnect(self, websocket: WebSocket) -> None:
        """
        Removes a WebSocket connection from the list of active
        connections.

        :param websocket: The WebSocket connection to remove.
        """
        self.active_connections.remove(websocket)
        logger.info("Client disconnected")

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
            logger.warning("Message buffered due to disconnection")

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
            logger.info("Sent buffered message: %s", buffered_message)

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
            await self.send_message(websocket, {"ping": "keepalive"}, session_id)
            logger.debug("Sent keepalive ping")

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
                logger.info("Received data: %s", data)
                await self._on_receive(websocket, session_id, data)

        except WebSocketDisconnect:
            await self._on_disconnect(websocket)
        finally:
            keepalive_task.cancel()
            logger.info("Keepalive task cancelled")


class LaunchConnectionManager(ConnectionManager):
    def __init__(self) -> None:
        super().__init__()
        self.agent_managers: Dict[str, AgentManager] = {}

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
            with at least two keys: `method` and `params`.

        methods:
            - init_external_repo_agent: Initialize an external
                repository agent.
            - get_external_repo_agents: Retrieve a list of external
                repository agents.
            - generate_subtasks: Generate subtasks based on an
                objective.
            - finetune_subtasks: Fine-tune subtasks based on an
                objective and instruction.
            - run_subtask: Run a specific subtask.
            - run_multiple_subtasks: Run multiple subtasks.
            - undo: Undo the last commit made by Aider.
            - shutdown: Shutdown the agent manager.

        """
        method = data.get("method")
        params = data.get("params", {})

        if method == "init_external_repo_agent":
            repo_dir = params.get("repo_dir")
            result = self.agent_managers[session_id].init_external_repo_agent(
                repo_dir)
            response = {"result": "Success" if result else "Failure"}
            await self.send_message(websocket, response, session_id)
            await self.send_message(websocket, ConnectionManager.END_OF_MESSAGE_RESPONSE, session_id)
            logger.info(
                "init_external_repo_agent result: %s",
                response['result'])

        elif method == "get_external_repo_agents":
            agents = str(
                self.agent_managers[session_id].get_external_repo_agents())
            response = {"result": agents}
            await self.send_message(websocket, response, session_id)
            await self.send_message(websocket, ConnectionManager.END_OF_MESSAGE_RESPONSE, session_id)
            logger.info("get_external_repo_agents result: %s", agents)

        elif method == "generate_subtasks":
            objective = params.get("objective")
            subtasks = json.dumps(await self.agent_managers[session_id].generate_subtasks(objective))
            response = {"result": subtasks}
            await self.send_message(websocket, response, session_id)
            await self.send_message(websocket, ConnectionManager.END_OF_MESSAGE_RESPONSE, session_id)
            logger.info("generate_subtasks result: %s", subtasks)

        elif method == "finetune_subtasks":
            objective = params.get("objective")
            instruction = params.get("instruction")
            subtasks = self.agent_managers[session_id].finetune_subtasks(
                objective, instruction)
            response = {"result": subtasks}
            await self.send_message(websocket, response, session_id)
            await self.send_message(websocket, ConnectionManager.END_OF_MESSAGE_RESPONSE, session_id)
            logger.info("finetune_subtasks result: %s", subtasks)

        elif method == "run_subtask":
            subtask = params.get("subtask")
            async for response in self.agent_managers[session_id].run_subtask(subtask):
                await self.send_message(websocket, {"result": response}, session_id)
                logger.info("run_subtask response: %s", response)
            await self.send_message(websocket, ConnectionManager.END_OF_MESSAGE_RESPONSE, session_id)

        elif method == "run_multiple_subtasks":
            subtasks = params.get("subtasks")
            async for response in self.agent_managers[session_id].run_multiple_subtasks(subtasks):
                await self.send_message(websocket, {"result": response}, session_id)
                logger.info(
                    "run_multiple_subtasks response: %s", response)
            await self.send_message(websocket, ConnectionManager.END_OF_MESSAGE_RESPONSE, session_id)

        elif method == "undo":
            self.agent_managers[session_id].undo()
            await self.send_message(websocket, ConnectionManager.END_OF_MESSAGE_RESPONSE, session_id)
            logger.info("Undo command sent to Agent")

        elif method == "shutdown":
            self.agent_managers[session_id].shutdown()
            await self.send_message(websocket, {"result": "shutdown"}, session_id)
            await self.send_message(websocket, ConnectionManager.END_OF_MESSAGE_RESPONSE, session_id)
            self.agent_managers.pop(session_id)
            logger.info("Shutdown initiated")
            #os.kill(os.getpid(), signal.SIGTERM)
