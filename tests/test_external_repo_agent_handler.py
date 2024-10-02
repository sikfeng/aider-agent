import asyncio
import logging
from logging.config import dictConfig

from raider_backend.handlers.external_repo_agent_handler import ExternalRepoAgentHandler
from raider_backend.logger import LOG_CONFIG
from raider_backend import utils

# Initialize logging
LOG_CONFIG['handlers']['fileHandler']['filename'] = utils.get_tmp_file("test_external_repo_agent_handler")
dictConfig(LOG_CONFIG)
logger = logging.getLogger("TestExternalRepoAgentHandler")


async def test():
    handler = ExternalRepoAgentHandler()
    handler.initialize_agent("agent1", "../tmp_repo")
    async for partial_response in handler.ask("agent1", "What does this repo do?"):
        logger.info(partial_response)

    async for partial_response in handler.ask("non-existent-id", "This should be an error"):
        logger.info(partial_response)
    
    handler.kill_all_agents()

def main():
    asyncio.run(test())

if __name__ == "__main__":
    main()