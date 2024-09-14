"""
Manages WebSocket connections and message buffering.

This class handles the lifecycle of WebSocket connections, including
accepting new connections, disconnecting clients, sending messages,
buffering messages for disconnected clients, and sending keepalive
pings at regular intervals.
"""
import asyncio
import json
import logging
import os
import signal

from fastapi import WebSocket, WebSocketDisconnect

from .agent_manager import AgentManager

logger = logging.getLogger("ConnectionManager")


class ConnectionManager:
    """
    Manages WebSocket connections and message buffering.
    """
    END_OF_MESSAGE_RESPONSE = {"<END_OF_MESSAGE>": "<END_OF_MESSAGE>"}

    def __init__(self):
        """
        Initializes the ConnectionManager with empty lists for active
        connections and message buffer.
        """
        self.active_connections = []
        self.agent_managers = {}
        self.message_buffer = []

    async def _on_connect(self, websocket: WebSocket, session_id: str):
        """
        Accepts a new WebSocket connection and adds it to the list of
        active connections.

        :param websocket: The WebSocket connection to accept.
        """
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket connection accepted")

        self.agent_managers[session_id] = AgentManager()

    async def _on_disconnect(self, websocket: WebSocket):
        """
        Removes a WebSocket connection from the list of active
        connections.

        :param websocket: The WebSocket connection to remove.
        """
        self.active_connections.remove(websocket)
        logger.info("Client disconnected")

    async def _on_receive(self, websocket: WebSocket, session_id: str, data):
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
            - undo_last_subtask: Undo the last executed subtask.
            - shutdown: Shutdown the agent manager.

        """
        method = data.get("method")
        params = data.get("params", {})

        if method == "init_external_repo_agent":
            repo_dir = params.get("repo_dir")
            result = self.agent_managers[session_id].init_external_repo_agent(
                repo_dir)
            response = {"result": "Success" if result else "Failure"}
            await self.send_message(websocket, response)
            await self.send_message(websocket, ConnectionManager.END_OF_MESSAGE_RESPONSE)
            logger.info(
                "init_external_repo_agent result: %s",
                response['result'])

        elif method == "get_external_repo_agents":
            agents = str(
                self.agent_managers[session_id].get_external_repo_agents())
            response = {"result": agents}
            await self.send_message(websocket, response)
            await self.send_message(websocket, ConnectionManager.END_OF_MESSAGE_RESPONSE)
            logger.info("get_external_repo_agents result: %s", agents)

        elif method == "generate_subtasks":
            objective = params.get("objective")
            subtasks = json.dumps(await self.agent_managers[session_id].generate_subtasks(objective))
            response = {"result": subtasks}
            await self.send_message(websocket, response)
            await self.send_message(websocket, ConnectionManager.END_OF_MESSAGE_RESPONSE)
            logger.info("generate_subtasks result: %s", subtasks)

        elif method == "finetune_subtasks":
            objective = params.get("objective")
            instruction = params.get("instruction")
            subtasks = self.agent_managers[session_id].finetune_subtasks(
                objective, instruction)
            response = {"result": subtasks}
            await self.send_message(websocket, response)
            await self.send_message(websocket, ConnectionManager.END_OF_MESSAGE_RESPONSE)
            logger.info("finetune_subtasks result: %s", subtasks)

        elif method == "run_subtask":
            subtask = params.get("subtask")
            async for response in self.agent_managers[session_id].run_subtask(subtask):
                await self.send_message(websocket, {"result": response})
                logger.info("run_subtask response: %s", response)
            await self.send_message(websocket, ConnectionManager.END_OF_MESSAGE_RESPONSE)

        elif method == "run_multiple_subtasks":
            subtasks = params.get("subtasks")
            async for response in self.agent_managers[session_id].run_multiple_subtasks(subtasks):
                await self.send_message(websocket, {"result": response})
                logger.info(
                    "run_multiple_subtasks response: %s", response)
            await self.send_message(websocket, ConnectionManager.END_OF_MESSAGE_RESPONSE)

        elif method == "undo_last_subtask":
            result = self.agent_managers[session_id].undo_last_subtask()
            response = {"result": "Success" if result else "Failure"}
            await self.send_message(websocket, response)
            await self.send_message(websocket, ConnectionManager.END_OF_MESSAGE_RESPONSE)
            logger.info(
                "undo_last_subtask result: %s",
                response['result'])

        elif method == "shutdown":
            self.agent_managers[session_id].shutdown()
            await self.send_message(websocket, {"result": "shutdown"})
            await self.send_message(websocket, ConnectionManager.END_OF_MESSAGE_RESPONSE)
            logger.info("Shutdown initiated")
            os.kill(os.getpid(), signal.SIGTERM)

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
        Sends keepalive pings to a specific WebSocket connection at
        regular intervals.

        :param websocket: The WebSocket connection to send the
            keepalive pings to.
        """
        while True:
            await asyncio.sleep(10)  # Adjust the interval as needed
            await self.send_message(websocket, {"ping": "keepalive"})
            logger.debug("Sent keepalive ping")

    async def websocket_endpoint(self,
                                 websocket: WebSocket,
                                 session_id: str,
                                 ):
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
            self.send_keepalive_pings(websocket))

        try:
            await self.send_buffered_messages(websocket)

            while True:
                data = await websocket.receive_json()
                logger.info("Received data: %s", data)
                await self._on_receive(websocket=websocket, session_id=session_id, data=data)

        except WebSocketDisconnect:
            await self._on_disconnect(websocket)
        finally:
            keepalive_task.cancel()
            logger.info("Keepalive task cancelled")
