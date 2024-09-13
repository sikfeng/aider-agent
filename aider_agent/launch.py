import asyncio
import logging
import os
import signal
import argparse
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from logging.config import dictConfig
from . import utils
from .agent_manager import AgentManager
from .logger import LOG_CONFIG

agent_manager = None

logger = logging.getLogger("WebSocketEndpoint")
app = FastAPI()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connection accepted")
    try:
        async def send_keepalive_pings():
            while True:
                await asyncio.sleep(10)  # Adjust the interval as needed
                await websocket.send_json({"ping": "keepalive"})
                logger.debug("Sent keepalive ping")

        keepalive_task = asyncio.create_task(send_keepalive_pings())

        while True:
            data = await websocket.receive_json()
            logger.info(f"Received data: {data}")
            method = data.get("method")
            params = data.get("params", {})

            if method == "init_external_repo_agent":
                repo_dir = params.get("repo_dir")
                result = agent_manager.init_external_repo_agent(repo_dir)
                await websocket.send_json({"result": "Success" if result else "Failure"})
                await websocket.send_json({"result": "</eos_token>"})
                logger.info(
                    f"init_external_repo_agent result: {'Success' if result else 'Failure'}")

            elif method == "get_external_repo_agents":
                agents = str(agent_manager.get_external_repo_agents())
                await websocket.send_json({"result": agents})
                await websocket.send_json({"result": "</eos_token>"})
                logger.info(f"get_external_repo_agents result: {agents}")

            elif method == "generate_subtasks":
                objective = params.get("objective")
                import json
                subtasks = json.dumps(await agent_manager.generate_subtasks(objective))
                await websocket.send_json({"result": subtasks})
                await websocket.send_json({"result": "</eos_token>"})
                logger.info(f"generate_subtasks result: {subtasks}")

            elif method == "finetune_subtasks":
                objective = params.get("objective")
                instruction = params.get("instruction")
                subtasks = agent_manager.finetune_subtasks(objective, instruction)
                await websocket.send_json({"result": subtasks})
                await websocket.send_json({"result": "</eos_token>"})
                logger.info(f"finetune_subtasks result: {subtasks}")

            elif method == "run_subtask":
                subtask = params.get("subtask")
                async for response in agent_manager.run_subtask(subtask):
                    await websocket.send_json({"result": response})
                    logger.info(f"run_subtask response: {response}")
                await websocket.send_json({"result": "</eos_token>"})

            elif method == "run_multiple_subtasks":
                subtasks = params.get("subtasks")
                async for response in agent_manager.run_multiple_subtasks(subtasks):
                    await websocket.send_json({"result": response})
                    logger.info(f"run_multiple_subtasks response: {response}")
                await websocket.send_json({"result": "</eos_token>"})

            elif method == "undo_last_subtask":
                result = agent_manager.undo_last_subtask()
                await websocket.send_json({"result": "Success" if result else "Failure"})
                await websocket.send_json({"result": "</eos_token>"})
                logger.info(
                    f"undo_last_subtask result: {'Success' if result else 'Failure'}")

            elif method == "shutdown":
                agent_manager.shutdown()
                await websocket.send_json({"result": "shutdown"})
                await websocket.send_json({"result": "</eos_token>"})
                logger.info("Shutdown initiated")
                os.kill(os.getpid(), signal.SIGTERM)

    except WebSocketDisconnect:
        logger.warning("Client disconnected")
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
        '--logname',
        type=str,
        help='Path to logfile',
        default="/tmp/manager.log")
    args = parser.parse_args()

    LOG_CONFIG['handlers']['fileHandler']['filename'] = utils.get_absolute_path(
        args.logname)
    if Path(LOG_CONFIG['handlers']['fileHandler']['filename']).is_file():
        # TODO: ask for user confirmation to overwrite logfile
        # for now I will just overwrite it anyways
        Path(LOG_CONFIG['handlers']['fileHandler']['filename']).unlink()
    dictConfig(LOG_CONFIG)

    global agent_manager
    agent_manager = AgentManager()
    import uvicorn  # Import Uvicorn for running the FastAPI app
    uvicorn.run(app, host="0.0.0.0", port=args.port)


# Run the application with Uvicorn
if __name__ == "__main__":
    main()
