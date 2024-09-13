"""
This module initializes and runs the FastAPI application with WebSocket
support for managing agent tasks.

The application provides a WebSocket endpoint to handle various agent
management tasks such as:

- Initializing external repository agents
- Generating and fine-tuning subtasks
- Running subtasks
- Shutting down the agent manager
"""
import asyncio
import logging
import os
import signal
import argparse
import json
from pathlib import Path
from logging.config import dictConfig

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

from . import utils
from .agent_manager import AgentManager
from .logger import LOG_CONFIG
from .connection_manager import ConnectionManager

agent_manager = AgentManager()
conn_manager = ConnectionManager()

logger = logging.getLogger("WebSocketEndpoint")
app = FastAPI()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint to handle various agent management tasks.

    This endpoint manages WebSocket connections and processes incoming
    messages to perform tasks such as initializing external repo
    agents, generating and fine-tuning subtasks, running subtasks, and
    shutting down the agent manager.

    :param websocket: The WebSocket connection instance.

    Methods:
        - init_external_repo_agent: Initialize an external repository
          agent.
        - get_external_repo_agents: Retrieve a list of external
          repository agents.
        - generate_subtasks: Generate subtasks based on an objective.
        - finetune_subtasks: Fine-tune subtasks based on an objective
          and instruction.
        - run_subtask: Run a specific subtask.
        - run_multiple_subtasks: Run multiple subtasks.
        - undo_last_subtask: Undo the last executed subtask.
        - shutdown: Shutdown the agent manager.

    :raises WebSocketDisconnect: If the WebSocket connection is
        disconnected.
    """
    await conn_manager.connect(websocket)
    keepalive_task = asyncio.create_task(
        conn_manager.send_keepalive_pings(websocket))

    END_OF_MESSAGE_RESPONSE = {"<END_OF_MESSAGE>": "<END_OF_MESSAGE>"}

    try:
        await conn_manager.send_buffered_messages(websocket)

        while True:
            data = await websocket.receive_json()
            logger.info("Received data: %s", data)
            method = data.get("method")
            params = data.get("params", {})

            if method == "init_external_repo_agent":
                repo_dir = params.get("repo_dir")
                result = agent_manager.init_external_repo_agent(repo_dir)
                response = {"result": "Success" if result else "Failure"}
                await conn_manager.send_message(websocket, response)
                await conn_manager.send_message(websocket, END_OF_MESSAGE_RESPONSE)
                logger.info(
                    "init_external_repo_agent result: %s",
                    response['result'])

            elif method == "get_external_repo_agents":
                agents = str(agent_manager.get_external_repo_agents())
                response = {"result": agents}
                await conn_manager.send_message(websocket, response)
                await conn_manager.send_message(websocket, END_OF_MESSAGE_RESPONSE)
                logger.info("get_external_repo_agents result: %s", agents)

            elif method == "generate_subtasks":
                objective = params.get("objective")
                subtasks = json.dumps(await agent_manager.generate_subtasks(objective))
                response = {"result": subtasks}
                await conn_manager.send_message(websocket, response)
                await conn_manager.send_message(websocket, END_OF_MESSAGE_RESPONSE)
                logger.info("generate_subtasks result: %s", subtasks)

            elif method == "finetune_subtasks":
                objective = params.get("objective")
                instruction = params.get("instruction")
                subtasks = agent_manager.finetune_subtasks(
                    objective, instruction)
                response = {"result": subtasks}
                await conn_manager.send_message(websocket, response)
                await conn_manager.send_message(websocket, END_OF_MESSAGE_RESPONSE)
                logger.info("finetune_subtasks result: %s", subtasks)

            elif method == "run_subtask":
                subtask = params.get("subtask")
                async for response in agent_manager.run_subtask(subtask):
                    await conn_manager.send_message(websocket, {"result": response})
                    logger.info("run_subtask response: %s", response)
                await conn_manager.send_message(websocket, END_OF_MESSAGE_RESPONSE)

            elif method == "run_multiple_subtasks":
                subtasks = params.get("subtasks")
                async for response in agent_manager.run_multiple_subtasks(subtasks):
                    await conn_manager.send_message(websocket, {"result": response})
                    logger.info("run_multiple_subtasks response: %s", response)
                await conn_manager.send_message(websocket, END_OF_MESSAGE_RESPONSE)

            elif method == "undo_last_subtask":
                result = agent_manager.undo_last_subtask()
                response = {"result": "Success" if result else "Failure"}
                await conn_manager.send_message(websocket, response)
                await conn_manager.send_message(websocket, END_OF_MESSAGE_RESPONSE)
                logger.info("undo_last_subtask result: %s", response['result'])

            elif method == "shutdown":
                agent_manager.shutdown()
                await conn_manager.send_message(websocket, {"result": "shutdown"})
                await conn_manager.send_message(websocket, END_OF_MESSAGE_RESPONSE)
                logger.info("Shutdown initiated")
                os.kill(os.getpid(), signal.SIGTERM)

    except WebSocketDisconnect:
        conn_manager.disconnect(websocket)
    finally:
        keepalive_task.cancel()
        logger.info("Keepalive task cancelled")


def main() -> None:
    """
    Main function to run the application.
    """
    parser = argparse.ArgumentParser(
        description="Launch the AgentManager with a Websocket endpoint.")
    parser.add_argument(
        '--port',
        type=int,
        help='Port of the agent',
        default=10000)
    parser.add_argument(
        '--logfile',
        type=str,
        help='Path to logfile',
        default="/tmp/manager.log")
    args = parser.parse_args()

    LOG_CONFIG['handlers']['fileHandler']['filename'] = utils.get_absolute_path(
        args.logfile)
    if Path(LOG_CONFIG['handlers']['fileHandler']['filename']).is_file():
        # TODO: ask for user confirmation to overwrite logfile
        # for now I will just overwrite it anyways
        Path(LOG_CONFIG['handlers']['fileHandler']['filename']).unlink()
    dictConfig(LOG_CONFIG)

    uvicorn.run(app, host="0.0.0.0", port=args.port)


# Run the application with Uvicorn
if __name__ == "__main__":
    main()
