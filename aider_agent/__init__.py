"""
This module initializes the `raider_backend` package and configures the
`litellm` library.

The `raider_backend` package includes the following components:
- `AgentManager`: Manages different agents within the system.
- `ConnectionManager`: Handles connections between agents and other
    components.
- `ExternalRepoAgentHandler`: Manages interactions with external
    repositories.
- `PlannerAgent`: Responsible for planning and decision-making tasks.
- `MainRepoAgent` and `ExternalRepoAgent`: Agents that interact with
    the main and external repositories, respectively.

The `litellm` library is configured to suppress debug information,
disable verbose output, and drop parameters.
"""
import litellm

from .repo_agent import MainRepoAgent, ExternalRepoAgent
from .planner_agent import PlannerAgent
from .external_repo_agent_handler import ExternalRepoAgentHandler
from .connection_manager import ConnectionManager
from .agent_manager import AgentManager

litellm.suppress_debug_info = True
litellm.set_verbose = False
litellm.drop_params = True
