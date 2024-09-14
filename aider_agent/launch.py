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
import argparse
import logging
from logging.config import dictConfig
from pathlib import Path
import os

from fastapi import FastAPI
import uvicorn

from . import utils
from .connection_manager import ConnectionManager
from .logger import LOG_CONFIG

conn_manager = ConnectionManager()

logger = logging.getLogger("WebSocketEndpoint")
app = FastAPI()
app.add_api_websocket_route(
    "/ws/{session_id}",
    conn_manager.websocket_endpoint)


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
    parser.add_argument(
        '--repo-dir',
        type=str,
        help='Directory of the main repository',
        default=".")
    args = parser.parse_args()

    args.repo_dir = utils.get_absolute_path(args.repo_dir)
    os.chdir(args.repo_dir)

    LOG_CONFIG['handlers']['fileHandler']['filename'] = utils.get_absolute_path(
        args.logfile)
    if Path(LOG_CONFIG['handlers']['fileHandler']['filename']).is_file():
        Path(LOG_CONFIG['handlers']['fileHandler']['filename']).unlink()
    dictConfig(LOG_CONFIG)

    uvicorn.run(app, host="0.0.0.0", port=args.port)


# Run the application with Uvicorn
if __name__ == "__main__":
    main()
