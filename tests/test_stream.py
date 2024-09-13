import asyncio
import json
import logging
from logging.config import dictConfig

import websockets

from aider_agent.logger import LOG_CONFIG
from aider_agent import utils

# Initialize logging
LOG_CONFIG['handlers']['fileHandler']['filename'] = utils.get_absolute_path(
    "/tmp/test_stream.log")
dictConfig(LOG_CONFIG)
logger = logging.getLogger("TestStream")

PORT = 10000


async def test_websocket_endpoint(uri, method, params=None):
    async with websockets.connect(uri, ping_interval=None) as websocket:
        request = {
            "method": method,
            "params": params or {}
        }
        await websocket.send(json.dumps(request))
        response_data = ""
        while True:
            response = await websocket.recv()
            partial_response_data = json.loads(response)
            if "ping" in partial_response_data:
                continue  # Ignore keepalive pings
            if partial_response_data == {
                    "<END_OF_MESSAGE>": "<END_OF_MESSAGE>"}:
                return response_data
            response_data += partial_response_data["result"]
            logger.info(partial_response_data["result"])


async def test():
    uri = f"ws://localhost:{PORT}/ws"

    external_repos = ["../continue"]
    task = "Make a basic hello world vscode extension"

    for repo_dir in external_repos:
        logger.info("Initializing external repo agent for %s", repo_dir)
        await test_websocket_endpoint(uri, "init_external_repo_agent", {"repo_dir": repo_dir})

    logger.info("Getting external repo agents")
    await test_websocket_endpoint(uri, "get_external_repo_agents")

    logger.info("Generating subtasks for task: %s", task)
    subtasks_response = await test_websocket_endpoint(uri, "generate_subtasks", {"objective": task})
    subtasks = json.loads(subtasks_response)

    for subtask in subtasks:
        logger.info("Running subtask: %s", subtask)
        await test_websocket_endpoint(uri, "run_subtask", {"subtask": subtask})

    await test_websocket_endpoint(uri, "undo_last_subtask")

    logger.info("Shutting down")
    await test_websocket_endpoint(uri, "shutdown")


def main():
    asyncio.run(test())


if __name__ == "__main__":
    main()
