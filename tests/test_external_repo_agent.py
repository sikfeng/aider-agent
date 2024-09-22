import asyncio
import json
import logging
from logging.config import dictConfig

import websockets

from raider_backend.logger import LOG_CONFIG
from raider_backend import utils

# Initialize logging
LOG_CONFIG['handlers']['fileHandler']['filename'] = utils.get_absolute_path(
    "/tmp/test_agent_manager.log")
dictConfig(LOG_CONFIG)
logger = logging.getLogger("TestExternalRepoAgent")

PORT = 8080


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
            elif partial_response_data == {
                    "<END_OF_MESSAGE>": "<END_OF_MESSAGE>"}:
                return response_data
            elif "error" in partial_response_data:
                response_data += str(partial_response_data["error"])
                logger.error(partial_response_data["error"])
            else:
                response_data += str(partial_response_data["result"])
                logger.info(partial_response_data["result"])


async def test():
    uri = f"ws://localhost:{PORT}/ws/tmp_session_id"

    logger.info("Getting repo map")
    await test_websocket_endpoint(uri, "get_repo_map")

    query = "What does the code in this repo implement?"
    logger.info("Asking query: %s", query)
    await test_websocket_endpoint(uri, "ask", {"msg": query})

    logger.info("Testing unknown method")
    await test_websocket_endpoint(uri, "bla bla bla")

def main():
    asyncio.run(test())


if __name__ == "__main__":
    main()
