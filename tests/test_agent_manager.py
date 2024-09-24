import asyncio
import json
import logging
from logging.config import dictConfig

import websockets

from raider_backend.logger import LOG_CONFIG
from raider_backend import utils
from raider_backend.connection_managers.base_connection_manager import BaseConnectionManager

# Initialize logging
LOG_CONFIG['handlers']['fileHandler']['filename'] = utils.get_absolute_path(
    "/tmp/test_agent_manager.log")
dictConfig(LOG_CONFIG)
logger = logging.getLogger("TestAgentManager")

PORT = 8000


async def test_websocket_endpoint(uri, method, params=None):
    async with websockets.connect(uri, ping_interval=None) as websocket:
        request = {
            "method": method,
            "params": params or {}
        }
        await websocket.send(json.dumps(request))
        response_data = []
        while True:
            response = await websocket.recv()
            partial_response_data = json.loads(response)
            if partial_response_data == BaseConnectionManager.KEEP_ALIVE_PING:
                continue  # Ignore keepalive pings
            elif partial_response_data == BaseConnectionManager.END_OF_MESSAGE_RESPONSE:
                return response_data

            if "info" in partial_response_data:
                logger.info(partial_response_data["info"])
            elif "warning" in partial_response_data:
                logger.warning(partial_response_data["warning"])
            elif "error" in partial_response_data:
                logger.error(partial_response_data["error"])
            elif "result" in partial_response_data:
                response_data += partial_response_data["result"]
                logger.info(partial_response_data["result"])


async def test():
    uri = f"ws://localhost:{PORT}/ws/tmp_session_id"

    external_repos = ["../continue"]
    task = "Make a basic hello world vscode extension"
    #task = "Add a reactjs webview to the extension"

    for repo_dir in external_repos:
        logger.info("Initializing external repo agent for %s", repo_dir)
        await test_websocket_endpoint(uri, "init_external_repo_agent", {"repo_dir": repo_dir})

    logger.info("Getting external repo agents")
    await test_websocket_endpoint(uri, "get_external_repo_agents")

    logger.info("Generating subtasks for task: %s", task)
    subtasks = await test_websocket_endpoint(uri, "generate_subtasks", {"objective": task})

    for subtask in subtasks:
        logger.info("Running subtask: %s", subtask)
        if subtask["task_type"] == "User action":
            logger.info("Current task relies on user action, skipping")
        elif subtask["task_type"] == "Command execution":
            await test_websocket_endpoint(uri, "generate_commands", {"subtask": subtask["task_body"]})
        elif subtask["task_type"] == "Coding":
            await test_websocket_endpoint(uri, "run_subtask", {"subtask": subtask["task_body"]})

    await test_websocket_endpoint(uri, "undo")

    logger.info("Shutting down")
    await test_websocket_endpoint(uri, "shutdown")


def main():
    asyncio.run(test())


if __name__ == "__main__":
    main()
