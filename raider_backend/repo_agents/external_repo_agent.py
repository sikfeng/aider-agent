import argparse
from typing import TYPE_CHECKING

from fastapi import FastAPI
import uvicorn

from raider_backend.repo_agents.base_repo_agent import BaseRepoAgent

if TYPE_CHECKING:
    from raider_backend.connection_managers.repo_agent_connection_manager import RepoAgentConnectionManager

class ExternalRepoAgent(BaseRepoAgent):
    """A class to manage the ExternalRepoAgent."""

    def __init__(
            self,
            model_name: str = "azure/gpt-4o",
            map_tokens: int = 8092) -> None:
        """Initialize the ExternalRepoAgent.

        :param modemodelame: The name of the model to use.
        :param map_tokens: Maximum number of tokens for the repo map.
        """
        super().__init__(model_name=model_name, map_tokens=map_tokens)

        self.repo_map = self._get_repo_map()

    def get_repo_map(self) -> str:
        # Expecting that external repo will not be modified
        # Hence we simply store the repo_map and just retrieve it.
        return self.repo_map
 
    def run(self, msg):
        raise RuntimeError("ExternalRepoAgent should NOT run any tasks!")

    def run_stream(self, msg):
        raise RuntimeError("ExternalRepoAgent should NOT run any tasks!")

def main() -> None:
    """
    Main function to run the agent application with WebSocket support.
    """
    parser = argparse.ArgumentParser(
        description="Start an aider instance with WebSocket support.")
    parser.add_argument(
        '--port',
        type=int,
        help='Port for WebSocket connections',
        default=8080)
    parser.add_argument(
        '--model-name',
        type=str,
        help='Name of the model to use',
        default="azure/gpt-4o")
    parser.add_argument(
        '--map-tokens',
        type=int,
        help='Maximum number of tokens for repo map',
        default=8092)
    args = parser.parse_args()

    # Set up the RepoAgentConnectionManager
    from raider_backend.connection_managers.repo_agent_connection_manager import RepoAgentConnectionManager
    conn_manager = RepoAgentConnectionManager()

    # Set up FastAPI with WebSocket support
    app = FastAPI()
    app.add_api_websocket_route("/ws/{session_id}", conn_manager.websocket_endpoint)
    app.add_api_route("/ping", conn_manager.ping)

    # Run the server
    uvicorn.run(app, host="localhost", port=args.port)

if __name__ == "__main__":
    main()