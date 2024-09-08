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
  - `aider_instance.py`: Manages the Aider agent.
  - `code_search.py`: Handles code search functionalities.
  - `manager.py`: Manages the overall process and agents.
  - `manager.py`: Manages the overall process and agents.
  - `test_stream.py`: Contains test functions for API endpoints.
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
python -m aider-agent.manager
```

## API Endpoints

The system provides several API endpoints for interacting with the agents:

- **Aider Agent Endpoints**:
  - `POST /run_stream`: Runs a stream with the given message.
  - `POST /ask`: Asks a question to the agent.
  - `GET /get_repo_map`: Retrieves the repository map.

- **Manager Endpoints**:
  - `POST /init_external_repo_agent`: Initializes an external repository agent.
  - `GET /get_external_repo_agents`: Retrieves a list of external repository agents.
  - `POST /generate_subtasks`: Generates subtasks for a given objective.
  - `POST /finetune_subtasks`: Finetunes subtasks based on the given instruction.
  - `POST /run_subtask`: Runs a specified subtask.
  - `GET /undo_last_subtask`: Undoes the last executed subtask.
  - `POST /confirm_run_subtasks`: Confirms and runs a list of subtasks.
  - `GET /shutdown`: Shuts down the system.


