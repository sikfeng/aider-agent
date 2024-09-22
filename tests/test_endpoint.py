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
    "/tmp/test_endpoint.log")
dictConfig(LOG_CONFIG)
logger = logging.getLogger("TestEndpoint")

PORT = 10000


async def test_websocket_endpoint(uri, main_repo_dir, method, params=None):
    async with websockets.connect(uri, ping_interval=None) as websocket:
        request = {
            "main_repo_dir": main_repo_dir,
            "method": method,
            "params": params or {}
        }
        await websocket.send(json.dumps(request))
        response_data = ""
        while True:
            response = await websocket.recv()
            partial_response_data = json.loads(response)
            if partial_response_data == BaseConnectionManager.KEEP_ALIVE_PING:
                continue  # Ignore keepalive pings
            elif partial_response_data == BaseConnectionManager.END_OF_MESSAGE_RESPONSE:
                return response_data

            if "error" in partial_response_data:
                response_data += partial_response_data["error"]
                logger.error(partial_response_data["error"])
            elif "result" in partial_response_data:
                response_data += partial_response_data["result"]
                logger.info(partial_response_data["result"])


async def test():
    uri = f"ws://localhost:{PORT}/ws/tmp_session_id"
    main_repo_dir = "/workspace/tmp_repo/"
    main_repo_dir2 = "/workspace/tmp_repo2/"

    external_repos = ["../continue"]
    external_repos2 = ["../react", "../sheetjs"]
    task = "Make a basic hello world vscode extension"

    for repo_dir in external_repos:
        logger.info("Initializing external repo agent %s on main repo %s", repo_dir, main_repo_dir)
        await test_websocket_endpoint(uri, main_repo_dir, "init_external_repo_agent", {"repo_dir": repo_dir})

    logger.info("Getting external repo agents of %s", main_repo_dir)
    await test_websocket_endpoint(uri, main_repo_dir, "get_external_repo_agents")

    for repo_dir in external_repos2:
        logger.info("Initializing external repo agent for %s", repo_dir)
        await test_websocket_endpoint(uri, main_repo_dir2, "init_external_repo_agent", {"repo_dir": repo_dir})

    logger.info("Getting external repo agents") # To verify that this is the same as before
    await test_websocket_endpoint(uri, main_repo_dir, "get_external_repo_agents")

    logger.info("Getting external repo agents")
    await test_websocket_endpoint(uri, main_repo_dir2, "get_external_repo_agents")

    logger.info("Generating subtasks for task: %s", task)
    subtasks_response = await test_websocket_endpoint(uri, main_repo_dir, "generate_subtasks", {"objective": task})
    subtasks = json.loads(subtasks_response)

    for subtask in subtasks:
        logger.info("Running subtask: %s", subtask)
        await test_websocket_endpoint(uri, main_repo_dir, "run_subtask", {"subtask": subtask})

    await test_websocket_endpoint(uri, main_repo_dir, "undo")

    logger.info("Shutting down")
    await test_websocket_endpoint(uri, main_repo_dir, "shutdown")


def main():
    asyncio.run(test())


if __name__ == "__main__":
    main()
