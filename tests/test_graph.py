
import logging
from logging.config import dictConfig

from raider_backend.logger import LOG_CONFIG
from raider_backend import utils

from raider_backend.graph import *

# Initialize logging
LOG_CONFIG['handlers']['fileHandler']['filename'] = utils.get_absolute_path(
    "/tmp/test_stream.log")
dictConfig(LOG_CONFIG)
logger = logging.getLogger("TestStream")

def main():
    # Parse the source codes
    nodes = []
    edges = []
    repos = [
        "/workspace/raider-backend/",
        "/workspace/auto-code-rover",
        "/workspace/claude-engineer",
        "/workspace/aider",
    ]
    for repo in repos:
        nodes_, edges_ = FileParser.parse_directory_first_pass(repo)
        nodes.extend(nodes_)
        edges.extend(edges_)

    # Initialize and construct the graph with admin credentials
    graph = CodeGraph(uri="neo4j://db:7687", user="neo4j", password="password")
    logger.info("Graph initialized")
    graph.reset()
    logger.info("Graph reset")
    graph.add_nodes_and_edges(nodes, edges)
    logger.info("Nodes and edges added")
    graph.send_query("What functions can help me with code parsing?")
    graph.close()

if __name__ == "__main__":
    main()
