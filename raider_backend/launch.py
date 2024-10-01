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

from fastapi import FastAPI
import uvicorn

from raider_backend import utils
from raider_backend.connection_managers.launch_connection_manager import LaunchConnectionManager
from raider_backend.connection_managers.web_raider_connection_manager import WebRaiderConnectionManager
from raider_backend.logger import LOG_CONFIG


def main() -> None:
    """
    Main function to run the application.

    This function sets up command-line arguments, configures logging,
    and starts the FastAPI application using Uvicorn.

    :return: None
    """
    # Set up command-line argument parser
    parser = argparse.ArgumentParser(
        description="Launch the AgentManager with a Websocket endpoint.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    
    # Add command-line arguments
    parser.add_argument(
        '--port',
        type=int,
        help='Port of the websocket',
        default=10000)
    parser.add_argument(
        '--logfile',
        type=str,
        help='Path to logfile',
        default="/tmp/manager.log")
    
    # Parse command-line arguments
    args = parser.parse_args()

    # Configure logging
    LOG_CONFIG['handlers']['fileHandler']['filename'] = utils.get_absolute_path(
        args.logfile)

    # Set up logging
    logger = logging.getLogger("WebSocketEndpoint")
    
    # Remove existing log file if it exists
    if Path(LOG_CONFIG['handlers']['fileHandler']['filename']).is_file():
        Path(LOG_CONFIG['handlers']['fileHandler']['filename']).unlink()
    
    # Apply logging configuration
    dictConfig(LOG_CONFIG)

    # Initialize the LaunchConnectionManager
    conn_manager = LaunchConnectionManager()
    web_raider_conn_manager = WebRaiderConnectionManager()

    # Initialize FastAPI application
    app = FastAPI()

    # Add WebSocket route to the application
    app.add_api_websocket_route(
        "/ws/{session_id}/{query_id}",
        conn_manager.websocket_endpoint)

    app.add_api_websocket_route(
        "/web_raider/ws/{session_id}/{query_id}",
        web_raider_conn_manager.websocket_endpoint)

    # Run the FastAPI application using Uvicorn
    uvicorn.run(app, host="localhost", port=args.port)


# Run the application with Uvicorn when the script is executed directly
if __name__ == "__main__":
    main()
