from raider_backend.graph import *

def main():
    # Parse the source code
    nodes, edges = FileParser.parse_directory_first_pass("/workspace/raider-backend/raider_backend/")

    # Initialize and construct the graph with admin credentials
    graph = CodeGraph(uri="neo4j://db:7687", user="neo4j", password="password")
    graph.add_nodes_and_edges(nodes, edges)
    graph.send_query("What is RepoAgent?")
    graph.close()

if __name__ == "__main__":
    main()
