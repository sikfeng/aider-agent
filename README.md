# Raider Backend Repository

This repository contains the implementation of the Raider Backend, a system designed to manage and interact with various agents for code analysis and task management.

## Table of Contents

- [Overview](#overview)
- [Directory Structure](#directory-structure)
- [Installation](#installation)
- [Usage](#usage)
- [API Endpoints](#api-endpoints)

## Overview

The Raider Backend system is designed to manage multiple agents that can perform various tasks such as running code, generating subtasks, and managing external repositories. The system is built using Python and provides both synchronous and asynchronous functionalities.

## Directory Structure

- `raider_backend/`: Main directory containing the core functionalities.
  - `__init__.py`: Initializes the `raider_backend` package.
  - `agent_manager.py`: Manages the overall process and agents.
  - `launch.py`: Launches the LaunchConnectionManager with a WebSocket endpoint.
  - `logger.py`: Configures logging for the application.
  - `parse.py`: Provides functionality to parse source code files and extract class, method, and function definitions using the tree-sitter library.
  - `planner_agent.py`: Manages the planning process for a given objective.
  - `prompts.py`: Contains prompt templates used by the agents for various tasks.
  - `repo_agent.py`: Defines BaseRepoAgent, ExternalRepoAgent, and MainRepoAgent classes.
  - `utils.py`: Utility functions for various tasks.
  - `connection_managers/`: Directory for connection management classes.
    - `base_connection_manager.py`: Defines the BaseConnectionManager class.
    - `agent_manager_connection_manager.py`: Implements the AgentManagerConnectionManager.
    - `launch_connection_manager.py`: Implements the LaunchConnectionManager.
    - `web_raider_connection_manager.py`: Implements the WebRaiderConnectionManager.
  - `handlers/`: Directory for handler classes.
    - `base_handler.py`: Defines the BaseHandler class.
    - `agent_manager_handler.py`: Implements the AgentManagerHandler.
    - `external_repo_agent_handler.py`: Implements the ExternalRepoAgentHandler.

## Installation

You can install the raider_backend package directly from PyPI using pip:

```sh
pip install raider_backend
```

This command will automatically download and install the latest version of raider_backend along with its dependencies.

For developers who want to work on the raider_backend codebase:

1. Clone the repository:
    ```sh
    git clone https://github.com/sikfeng/raider-backend.git
    cd raider-backend
    ```

2. Install the package in editable mode:
    ```sh
    pip install -e .
    ```
   This command installs the package in editable mode (-e), which is useful for development as it allows you to modify the source code and immediately see the effects without reinstalling.

3. (Optional) Build the Docker image:
    ```sh
    ./build_docker.sh
    ```

After installation, you can import and use the raider_backend package in your Python scripts or interactive sessions.

## Usage

To run the main application, execute:
```sh
launch_endpoint
```

The usage information is as follows:
```
usage: launch_endpoint [-h] [--port PORT] [--logfile LOGFILE]

Launch the AgentManager with a Websocket endpoint.

options:
  -h, --help         show this help message and exit
  --port PORT        Port of the websocket (default: 10000)
  --logfile LOGFILE  Path to logfile (default: /tmp/manager.log)
```

### Running in a Devcontainer

1. **Open the repository in Visual Studio Code**:
    - Ensure you have the [Remote - Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) extension installed.

2. **Reopen in Container**:
    - Click on the green button in the bottom-left corner of the VS Code window.
    - Select `Reopen in Container`.

3. **Post Start Command**:
    - After the container starts, the `postStartCommand` defined in `.devcontainer/devcontainer.json` will automatically install the necessary dependencies.

**Note**:  The devcontainer will only mount the parent directory of this repository as the VS Code workspace. Therefore, the repository you are working on and any repository you want to use as context must be within the parent directory of the current repository.

**Environment Variables**: You can add environment variables such as API keys to the `.env` file within the `.devcontainer` directory. This will ensure that these variables are available within the development container.

This will set up the development environment inside a Docker container, ensuring consistency across different development setups.

## API Endpoints

The system provides WebSocket endpoints for interacting with the agents:

### 1. Agent Manager Endpoint

- **WebSocket Endpoint**: `ws://<host>:<port>/ws/{session_id}`

  This endpoint is managed by the `AgentManagerConnectionManager`, which acts as an intermediary between the external client and the `AgentManager`.

  When sending messages to this endpoint, use the following JSON format:

  ```json
  {
    "method": "<method_name>",
    "params": {
      "<param1>": "<value1>",
      "<param2>": "<value2>",
      ...
    }
  }
  ```

  Available methods include:

  - `init_external_repo_agent`: Initializes an external repository agent.
    - **Params**: 
      - `repo_dir` (str): The directory of the repository.
      - `model_name` (str, optional): The name of the model to use. Default is "azure/gpt-4o".
      - `timeout` (int, optional): Timeout for agent initialization. Default is 10 seconds.

  - `get_external_repo_agents`: Retrieves a list of external repository agents.

  - `generate_subtasks`: Generates subtasks for a given objective.
    - **Params**: 
      - `objective` (str): The main objective.

  - `run_subtask`: Runs a specified subtask.
    - **Params**: 
      - `subtask` (str): The subtask to run.

  - `generate_commands`: Generates commands for a given subtask.
    - **Params**:
      - `subtask` (str): The subtask for which to generate commands.

  - `undo`: Undoes the last commit.

  - `shutdown`: Shuts down the AgentManager.

  - `disable_external_repo_agent`: Disables an external repository agent.
    - **Params**:
      - `agent_id` (str): The ID of the agent to disable.

  - `enable_external_repo_agent`: Enables a previously disabled external repository agent.
    - **Params**:
      - `agent_id` (str): The ID of the agent to enable.

#### Example

To initialize an external repository agent, the data format would be:

```json
{
  "main_repo_dir": "/path/to/main/repo",
  "method": "init_external_repo_agent",
  "params": {
    "repo_dir": "/path/to/external/repo",
    "model_name": "azure/gpt-4o",
    "timeout": 15
  }
}
```

The `LaunchConnectionManager` will process this request, forward it to the appropriate `AgentManagerHandler`, and return the response through the WebSocket connection.

### 2. Web Raider Endpoint

- **WebSocket Endpoint**: `ws://<host>:<port>/web_raider/ws/{session_id}`

  This endpoint is managed by the `WebRaiderConnectionManager`, which handles queries for the Web Raider functionality.

  When sending messages to this endpoint, use the following JSON format:

  ```json
  {
    "method": "query",
    "params": {
      "user_query": "<your_query>"
    }
  }
  ```

  Available methods:

  - `query`: Sends a query to the Web Raider pipeline.
    - **Params**: 
      - `user_query` (str): The query to be processed by Web Raider.

#### Example

To send a query to Web Raider, the data format would be:

```json
{
  "method": "query",
  "params": {
    "user_query": "Find a programming language agnostic AST parser"
  }
}
```

The `WebRaiderConnectionManager` will process this request, forward it to the Web Raider pipeline, and return the response through the WebSocket connection.
