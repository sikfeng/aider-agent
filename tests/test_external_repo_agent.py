import asyncio
import json
import logging
from logging.config import dictConfig

import websockets

from raider_backend.logger import LOG_CONFIG
from raider_backend import utils
from raider_backend.connection_managers.base_connection_manager import BaseConnectionManager

# Initialize logging
LOG_CONFIG['handlers']['fileHandler']['filename'] = utils.get_tmp_file("test_external_repo_agent")
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
        while True:
            response = await websocket.recv()
            partial_response_data = json.loads(response)
            if partial_response_data == BaseConnectionManager.KEEP_ALIVE_PING:
                continue  # Ignore keepalive pings
            elif partial_response_data == BaseConnectionManager.END_OF_MESSAGE_RESPONSE:
                return

            if "info" in partial_response_data:
                logger.info(partial_response_data["info"])
                yield partial_response_data
            elif "warning" in partial_response_data:
                logger.warning(partial_response_data["warning"])
                yield partial_response_data
            elif "error" in partial_response_data:
                logger.error(partial_response_data["error"])
                yield partial_response_data
            elif "result" in partial_response_data:
                logger.info(partial_response_data["result"])
                yield partial_response_data


async def test():
    uri = f"ws://localhost:{PORT}/ws/tmp_session_id"

    logger.info("Getting repo map")
    async for _ in test_websocket_endpoint(uri, "get_repo_map"):
        pass

    query = "What does the code in this repo implement?"
    logger.info("Asking query: %s", query)
    async for _ in test_websocket_endpoint(uri, "ask", {"msg": query}):
        pass

    logger.info("Testing unknown method")
    async for _ in test_websocket_endpoint(uri, "bla bla bla"):
        pass

def main():
    asyncio.run(test())


if __name__ == "__main__":
    main()
