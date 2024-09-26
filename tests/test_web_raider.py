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
    "/tmp/test_web_raider.log")
dictConfig(LOG_CONFIG)
logger = logging.getLogger("TestWebRaider")

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
    uri = f"ws://localhost:{PORT}/web_raider/ws/tmp_session_id"
    query = "Find a programming language agnostic AST parser"

    await test_websocket_endpoint(uri, "query", {"user_query": query})


def main():
    asyncio.run(test())


if __name__ == "__main__":
    main()
