# Aider Agent Repository

This repository contains the implementation of the Aider Agent, a system designed to manage and interact with various agents for code analysis and task management.

## Table of Contents

- [Overview](#overview)
- [Directory Structure](#directory-structure)
- [Installation](#installation)
- [Usage](#usage)
- [API Endpoints](#api-endpoints)

## Overview

The Aider Agent system is designed to manage multiple agents that can perform various tasks such as running code, generating subtasks, and managing external repositories. The system is built using Python and provides both synchronous and asynchronous functionalities.

## Directory Structure

- `aider_agent/`: Main directory containing the core functionalities.
  - `__init__.py`: Initializes the `aider_agent` package and configures the `litellm` library.
  - `agent_manager.py`: Manages the overall process and agents.
  - `connection_manager.py`: Manages WebSocket connections and message buffering.
  - `external_repo_agent_handler.py`: Manages interactions with ExternalRepoAgent.
  - `launch.py`: Launches the ConnectionManager with a WebSocket endpoint.
  - `logger.py`: Configures logging for the application.
  - `parse.py`: Provides functionality to parse source code files and extract class, method, and function definitions using the tree-sitter library.
  - `planner_agent.py`: Manages the planning process for a given objective.
  - `prompts.py`: Contains prompt templates used by the agents for various tasks.
  - `repo_agent.py`: Manages MainRepoAgent and ExternalRepoAgent.
  - `utils.py`: Utility functions for various tasks.

## Installation

1. Clone the repository:
    ```sh
    git clone https://github.com/sikfeng/aider-agent.git
    cd aider-agent
    ```

2. Install the required dependencies:
    ```sh
    pip install -r requirements.txt
    ```

3. (Optional) Build the Docker image:
    ```sh
    ./build_docker.sh
    ```

## Usage

To run the main application, execute:
```sh
launch_endpoint
```

## API Endpoints

The system provides several WebSocket methods for interacting with the agents:

- **Repo Agent Methods**:
  - `POST /msg`: Sends a message to the agent.
    - **Params**: 
      - `msg` (str): The message to send.
  - `POST /run_stream`: Runs a stream with the given message.
    - **Params**: 
      - `msg` (str): The message to run in the stream.
  - `POST /ask`: Asks a question to the agent.
    - **Params**: 
      - `msg` (str): The question to ask.
  - `GET /get_repo_map`: Retrieves the repository map.
  - `GET /ping`: Pings the agent to check if it's alive.

- **Manager Methods** :(WebSocket endpoint: `ws://<host>:<port>/ws/{session_id}`)
  - `init_external_repo_agent`: Initializes an external repository agent.
    - **Params**: 
      - `repo_dir` (str): The directory of the repository.
  - `get_external_repo_agents`: Retrieves a list of external repository agents.
  - `generate_subtasks`: Generates subtasks for a given objective.
    - **Params**: 
      - `objective` (str): The main objective.
  - `finetune_subtasks`: Finetunes subtasks based on the given instruction.
    - **Params**: 
      - `objective` (str): The main objective.
      - `instruction` (str): Additional instructions for finetuning.
  - `run_subtask`: Runs a specified subtask.
    - **Params**: 
      - `subtask` (str): The subtask to run.
  - `run_multiple_subtasks`: Confirms and runs a list of subtasks.
    - **Params**: 
      - `subtasks` (List[str]): The list of subtasks to run.
  - `undo_last_subtask`: Undoes the last executed subtask.
  - `shutdown`: Shuts down the system.

### WebSocket Data Format

For each WebSocket method, the data should be sent in the following JSON format:

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

#### Example

To initialize an external repository agent, the data format would be:

```json
{
  "method": "init_external_repo_agent",
  "params": {
    "repo_dir": "/path/to/repo"
  }
}
```
