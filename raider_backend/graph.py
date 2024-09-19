import neo4j
from neo4j import GraphDatabase
from grep_ast import filename_to_lang
from tree_sitter_languages import get_parser
import re
import logging
from logging.config import dictConfig
from . import utils
import os
from .logger import LOG_CONFIG

# Initialize logging
LOG_CONFIG['handlers']['fileHandler']['filename'] = utils.get_absolute_path(
    "/tmp/test_stream.log")
dictConfig(LOG_CONFIG)
logger = logging.getLogger("TestGraph")

# Currently, I only have Neo4j community edition, which does not support multiple databases.
# I could add multiple repositories and just search all of them together?

class CodeGraph:
    # Graph Schema (https://www.arxiv.org/pdf/2408.03910)
    schema = """
## Nodes
1. **MODULE**:
   - **Attributes**:
     - `name` (String): Name of the module (dotted name)
     - `file_path` (String): File path of the module

2. **CLASS**:
   - **Attributes**:
     - `name` (String): Name of the class
     - `file_path` (String): File path of the class
     - `signature` (String): The signature of the class
     - `code` (String): Full code of the class

3. **FUNCTION**:
   - **Attributes**:
     - `name` (String): Name of the function
     - `file_path` (String): File path of the function
     - `code` (String): Full code of the function
     - `signature` (String): The signature of the function

4. **FIELD**:
   - **Attributes**:
     - `name` (String): Name of the field
     - `file_path` (String): File path of the field
     - `class` (String): Name of the class the field belongs to

5. **METHOD**:
   - **Attributes**:
     - `name` (String): Name of the method
     - `file_path` (String): File path of the method
     - `class` (String): Name of the class the method belongs to
     - `code` (String): Full code of the method
     - `signature` (String): The signature of the method

6. **GLOBAL_VARIABLE**:
   - **Attributes**:
     - `name` (String): Name of the global variable
     - `file_path` (String): File path of the global variable
     - `code` (String): The code segment in which the global variable is defined.

## Edges
1. **CONTAINS**:
   - **Source**: MODULE
   - **Target**: CLASS or FUNCTION or GLOBAL_VARIABLE

2. **HAS_METHOD**:
   - **Source**: CLASS
   - **Target**: METHOD

3. **HAS_FIELD**:
   - **Source**: CLASS
   - **Target**: FIELD

4. **INHERITS**:
   - **Source**: CLASS
   - **Target**: CLASS (base class)

5. **USES**:
   - **Source**: FUNCTION or METHOD
   - **Target**: GLOBAL_VARIABLE or FIELD
   - **Attributes**:
     - `source_association_type` (String): `FUNCTION`, `METHOD`
     - `target_association_type` (String): `GLOBAL_VARIABLE`, `FIELD`
"""
    node_query_template = "MERGE (n:{type} {{name: $name, file_path: $file_path, class: $class, code: $code, signature: $signature}})"
    edge_query_template = """
MATCH (source:{source_type} {{name: $source_name, file_path: $source_file_path, class: $source_class, code: $source_code, signature: $source_signature}}), (target:{target_type} {{name: $target_name, file_path: $target_file_path, class: $target_class, code: $target_code, signature: $target_signature}})
MERGE (source)-[r:{edge_type} {{source_association_type: $source_association_type, target_association_type: $target_association_type}}]->(target)
"""

    def __init__(self, uri, user, password, model_name="azure/gpt-4o"):
        self.model_name = model_name
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.driver.verify_connectivity() # Will throw exception if connection fails

    def close(self):
        self.driver.close()

    def reset(self):
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    def create_node(self, params):
        query = CodeGraph.node_query_template.format(type=params["type"])
        for param in ["name", "file_path", "class", "code", "signature"]:
            if param not in params:
                query = query.replace(f", {param}: ${param}", "")
                query = query.replace(f"{param}: ${param},", "")
                query = query.replace(f"{param}: ${param}", "")  # handle single or trailing ones
        with self.driver.session() as session:
            session.run(query, **params)
    
    def create_edge(self, params):
        query = CodeGraph.edge_query_template.format(source_type=params["source_type"], target_type=params["target_type"], edge_type=params["edge_type"])
        for param in ["name", "file_path", "class", "code", "signature"]:
            for param_prefix in ["source_", "target_"]:
                if param_prefix + param not in params:
                    query = query.replace(f", {param}: ${param_prefix}{param}", "")
                    query = query.replace(f"{param}: ${param_prefix}{param},", "")
                    query = query.replace(f"{param}: ${param_prefix}{param}", "")  # handle single or trailing ones
        for param in ["source_association_type", "target_association_type"]:
            if param not in params:
                query = query.replace(f", {param}: ${param}", "")
                query = query.replace(f"{param}: ${param},", "")
                query = query.replace(f"{param}: ${param}", "")  # handle single or trailing ones
        with self.driver.session() as session:
            session.run(query, **params)

    def add_nodes_and_edges(self, nodes=[], edges=[]):
        for node in nodes:
            self.create_node(node)
        for edge in edges:
            self.create_edge(edge)
    
    def send_query(self, query):
        # Note: the community edition of Neo4j does not support user roles, hence we must use the admin user to execute queries.
        # It is possible that it would perform "bad" queries, so we need to be careful.
        system_prompt = """
# ROLE #
You are a software developer maintaining a large project.
Your task is to answer various questions related to the code project raised by users, which may include asking questions, fixing bugs, adding function comments, adding new requirements, etc.

The question contains a description marked between <questions> and </questions>.
You can write text queries to retrieve information from a given code graph database to collect information, and then write answers to user questions.

# LIMITATIONS #
1. You can only process text content, including code;
2. You cannot interpret graphical or visual content;
3. You have no access to the original project code instead of the information stored in the code graph database;

# CODE GRAPH DATABASE #
The code graph database is derived from static parsing of the project. Another code assistant, proficient in Cypher and graph databases, \
will translate your text queries into Cypher queries to extract the needed information based on your problem statement. \
The database is assumed to be devoid of issues. If unexpected responses occur during querying, it might be due to a faulty query, \
or missing nodes or edges resulting from indirect calls, dynamic behaviors, and complex control flows.

# SCHEMA OF THE CODE GRAPH DATABASE #
{db_schema}
"""
        system_prompt = system_prompt.format(db_schema=CodeGraph.schema)

        user_prompt = """
### User's Requirements:
<questions>
{user_query}
<\questions>

First, analyze the above given issue and current context. Your ultimate goal is to analyze user's question and answer it.
Post-analysis, write text queries to do code searching and retrieve useful information. Answer in the following format:
[start_of_analysis]
<detailed_analysis>
[end_of_analysis]

[start_of_code_search]
### Text Query 1
<text_description_of_the_query>

### Text Query 2
<text_description_of_the_query>

...
### Text Query n
<text_description_of_the_query>
[end_of_code_search]

Notes:
- Adhere strictly to the provided schema, and avoid creating your own nodes and edges.
- Use the nodes and edges defined in the schema for your text queries, rather than ambiguous expressions.
- If the desired class, method, or function is not found in the specified module, consider: 1). re-exporting, 2). incomplete module path, 3). the module comes from external libraries. Especially, the completeness of a module path is very CRUCIAL, try to figure it out clearly.
- In each round, you can write only ONE text queries during the code search phase.
- Your text queries should be CONCISE, ACCURATE and INFORMATIVE.
- The logic to query whether a code snippet of a particular node contains a specific string has been temporarily disabled.

Preferred Text Queries Examples:
- List the signatures of all methods of the class `User` in the file `app/models/user.py`.
- Retrieve the names of all functions within the `a.b.c.d` module.
- Find the file paths and signatures of the functions with `filter` in their names.
- Retrieve the code of the method named `get_name` from the class `Profile` or any of its base classes.
- Get the modules which contains `utils` in their names. (Encouraged to perform a fuzzy search like this when the module path is not complete.)

Unpreferred Text Queries Examples:
- List all the methods that have something to do with user authentication, including those that might be inherited from parent classes, particularly those which are in app.models or possibly elsewhere.
    - The query is too lengthy and contains too many unnecessary details, making it complex to understand and process.
- List all methods in module `users`.
    - If `users` is not an existing module, the query will be invalid. Make sure the path is correct.
- Retrieve the names and file paths of all global variables in the project.
    - The query is not informative and redundant.
"""
        user_prompt = user_prompt.format(user_query=query)
        response = utils.llm(self.model_name)(system_prompt=system_prompt, user_prompt=user_prompt)
        logger.info("Response: %s", response)
        match = re.search(r"\[start_of_code_search\](.*?)\[end_of_code_search\]", response, re.DOTALL)
        logger.info("Queries: %s", match.group(1))
        
        system_prompt = """
# ROLE #
You are a Cypher code assistant proficient in querying graph databases. Your task is to write Cypher queries based on the queries provided by the code assistant specializing in cross-file code tasks. Your goal is to extract the relevant information from the code graph database to support the adding new code requirements for code.

# LIMITATIONS #
1. You cannot modify or add to the schema of the code graph database.
2. You must rely on the problem statements and constraints given by the cross-file code completion assistant.

# CODE GRAPH DATABASE #
The code graph database is derived from static parsing of the project. You will write Cypher queries to extract necessary information based on the text queries provided. The database is presumed error-free. If unexpected responses arise, it might be due to incorrect queries, missing nodes, or edges from indirect calls, dynamic behaviors, and complex control flows.

# SCHEMA OF THE CODE GRAPH DATABASE #
{schema}
"""
        user_prompt = f"""
#### Text Queries:
{match.group(1)}
""" + \
"""

#### Task Instructions:
Your task is to decompose the given text queries into several simple ones and try to use precise or fuzzy matching, and then translate the decomposed text queries into the corresponding Cypher queries. You answer should follow the below formats:

[start_of_cypher_queries]
### Query 1
**decomposed text query**:
```cypher
<cypher_query>
```

### Query 2
**decomposed text query**:
```cypher
<cypher_query>
```
...

### Query n
**decomposed text query**:
```cypher
<cypher_query>
```
[end_of_cypher_queries]

#### NOTE:
- If the attributes to be returned by the query are not specified, please return the entire node.
- The logic to query whether a code snippet of a particular node contains a specific string has been temporarily disabled

Here are some useful tips:
1. Try adding exception handling logic (e.g., `OPTIONAL`, `OR`) to return error information or handle edge cases in Cypher queries.
2. Use appropriate Cypher patterns and aggregation functions to handle exceptions and edge cases that may occur in queries.
3. Try to use the nodes (CLASS, METHOD, FUNCTION, FIELD, GLOBAL_VARIABLE, MODULE) and egdes (CONTAINS, HAS_METHOD, HAS_FIELD, USES, INHERITES) in the schema to rewrite text queries instead of using ambiguous expressions like `attributes` or `objects`.
4. Use fuzzy matching when retrieving nodes to avoid issues with absolute paths. For example, use the following Cypher query: `WHERE m.name =~ '.*<node_name>'`

#### Useful Example:
1. Query all methods and fields under a Class under a Module:
```cypher
MATCH (mod:MODULE {name: '<module name>'})
MATCH (mod)-[:CONTAINS]->(cls:CLASS {name: '<class name>'})
MATCH (cls)-[:HAS_METHOD]->(method:METHOD)
MATCH (cls)-[:HAS_FIELD]->(field:FIELD)
RETURN method.name, field.code
```
2. Query all fields under a Class:
```cypher
MATCH (c:CLASS {name: 'YourClassName'})-[:HAS_FIELD]->(f) RETURN f.name, f.code
```
4. Query the code of a specific method:
```cypher
MATCH (m:METHOD {name: 'yourMethodName'}) RETURN m.code
```
"""
        system_prompt = system_prompt.format(schema=CodeGraph.schema)
        response = utils.llm(self.model_name)(system_prompt=system_prompt, user_prompt=user_prompt)
        logger.info(response)

        def extract_cypher_queries(response):
            import re
            """
            Check if there are shell commands in the Aider agent
            response.

            :param aider_response: The response from the
                Aider agent.
            :return: The shell command if found, otherwise None.
            """
            # List of shell code block markers
            shell_markers = [
                'cypher'
            ]

            # Create a regex pattern to match any of the shell code block
            # markers
            shell_code_pattern = re.compile(
                r'```(?:' + '|'.join(shell_markers) + r')(.*?)```',
                re.DOTALL | re.IGNORECASE)

            # Find all matches
            matches = shell_code_pattern.findall(response)

            if not matches:
                return None

            return matches
        
        cypher_queries = extract_cypher_queries(response)
        logger.info("Cypher queries: %s", cypher_queries)

        cypher_results = []
        for cypher_query in cypher_queries:
            with self.driver.session() as session:
                try:
                    query_results = session.run(cypher_query)
                    print(query_results.keys())
                    for query_result in query_results:
                        logger.debug("Query result: %s", query_result)
                        cypher_results.append(query_result)
                except neo4j.exceptions.CypherSyntaxError as e:
                    logger.warning("Error parsing cypher query %s: %s", cypher_query, exc_info=True)
        
        logger.info("Cypher query results: %s", cypher_results)
        if not cypher_results:
            return
        #return cypher_query_results

        system_prompt = """
You are an expert at interpreting the results of Cypher queries executed on a codebase knowledge graph. Given the following query result, generate a natural language summary that answers the user's original question.
"""
        # Complete prompt with user query and results
        user_prompt = """
Original Query: {query}

Cypher Query: {cypher_queries}

Cypher Result: {cypher_results}
"""
        user_prompt = user_prompt.format(query=query, cypher_queries=cypher_queries, cypher_results=str(cypher_results))
        response = utils.llm(self.model_name)(system_prompt=system_prompt, user_prompt=user_prompt)
        logger.info("Summary: %s", response)
        return response


class FileParser:
    @staticmethod
    def parse_source_file_first_pass(file_path):
        # This is the first pass. This will get the list of nodes and edges internally
        # The second pass is needed for edges between modules and classes
        file_full_path = utils.get_absolute_path(file_path)
        try:
            lang = filename_to_lang(file_full_path)

            # Read the file content
            with open(file_full_path, 'r', encoding="utf-8") as file:
                file_content = file.read()

            # Initialize tree-sitter parser with language
            parser = get_parser(lang)

            # Parse the file content
            tree = parser.parse(bytes(file_content, "utf8"))

        except Exception:
            # Return None if parsing fails
            print("Error: ", file_full_path)
            return None

        nodes = []
        edges = []

        module_name = os.path.splitext(os.path.basename(file_full_path))[0]  # Get module name from filename
        nodes.append({
            "type": "MODULE",
            "name": module_name,
            "file_path": file_full_path,
        })
        
        # Traverse the tree to find import nodes
        def traverse(node, parent_class=None, parent_function=None, parent_method=None):
            if node.type == "class_definition":
                class_name = node.child_by_field_name("name").text.decode('utf-8')
                class_code = file_content[node.start_byte:node.end_byte] # TODO: consider only leaving line numbers
                nodes.append({
                    "type": "CLASS",
                    "name": class_name,
                    "file_path": file_full_path,
                    "signature": "", # TODO but modelscope also ignored it lol https://github.com/modelscope/modelscope-agent/blob/195459c09fe7c99d07e5e3d735069e2b59b2bd50/modelscope_agent/environment/graph_database/indexer/my_client.py#L73
                    "code": class_code,
                })
                edges.append({
                    'edge_type': "CONTAINS",
                    'source_type': "MODULE",
                    'source_name': module_name,
                    "source_file_path": file_full_path,
                    "target_type": "CLASS",
                    "target_name": class_name,
                    "target_file_path": file_full_path,
                })
                parent_class = class_name

                # Check for a base class
                base_classes_node = node.child_by_field_name("superclasses")
                if base_classes_node:
                    base_class_name = base_classes_node.text.decode('utf-8')
                    for child in base_classes_node.children:
                        if child.type == "identifier":
                            base_class_name = child.text.decode('utf-8')
                            nodes.append({
                                "type": "CLASS",
                                "name": base_class_name,
                                "file_path": file_full_path, # TODO: need to implement checking later, check if base class is in this module
                                "signature": "", # TODO but modelscope also ignored it lol https://github.com/modelscope/modelscope-agent/blob/195459c09fe7c99d07e5e3d735069e2b59b2bd50/modelscope_agent/environment/graph_database/indexer/my_client.py#L73
                                "code":base_class_name, # TODO: need to implement checking later, check if base class is in this module
                            })
                            edges.append({
                                'edge_type': "INHERITS",
                                "source_type": "CLASS",
                                'source_name': class_name,
                                "source_file_path": file_full_path,
                                "target_type": "CLASS",
                                "target_name": base_class_name,
                            })
            elif node.type == "function_definition":
                if parent_class:
                    method_name = node.child_by_field_name("name").text.decode('utf-8')
                    method_code = file_content[node.start_byte:node.end_byte] # TODO: consider only leaving line numbers
                    nodes.append({
                        "type": "METHOD",
                        "name": method_name,
                        "file_path": file_full_path,
                        "class": parent_class,
                        "signature": "", # TODO but modelscope also ignored it lol https://github.com/modelscope/modelscope-agent/blob/195459c09fe7c99d07e5e3d735069e2b59b2bd50/modelscope_agent/environment/graph_database/indexer/my_client.py#L73
                        "code": method_code,
                    })
                    edges.append({
                        'edge_type': "HAS_METHOD",
                        "source_type": "CLASS",
                        "source_name": parent_class,
                        "source_file_path": file_full_path,
                        "target_type": "METHOD",
                        "target_name": method_name,
                        "target_file_path": file_full_path,
                    })
                    parent_method = method_name
                else:
                    function_name = node.child_by_field_name("name").text.decode('utf-8')
                    function_code = file_content[node.start_byte:node.end_byte] # TODO: consider only leaving line numbers
                    nodes.append({
                        "type": "FUNCTION",
                        "name": function_name,
                        "file_path": file_full_path,
                        "signature": "", # TODO but modelscope also ignored it lol https://github.com/modelscope/modelscope-agent/blob/195459c09fe7c99d07e5e3d735069e2b59b2bd50/modelscope_agent/environment/graph_database/indexer/my_client.py#L73
                        "code": function_code,
                    })
                    edges.append({
                        'edge_type': "CONTAINS",
                        "source_type": "MODULE",
                        "source_name": module_name,
                        "source_file_path": file_full_path,
                        "target_type": "FUNCTION",
                        "target_name": function_name,
                        "target_file_path": file_full_path,
                    })
                    parent_function = function_name
                pass
            elif node.type == "assignment":
                if parent_class:
                    field_name = node.child_by_field_name("left").text.decode("utf-8")
                    nodes.append({
                        "type": "FIELD",
                        "name": field_name,
                        "file_path": file_full_path,
                        "class": parent_class,
                    })
                    edges.append({
                        'edge_type': "HAS_FIELD",
                        "source_type": "CLASS",
                        "source_name": parent_class,
                        "source_file_path": file_full_path,
                        "target_type": "FIELD",
                        "target_name": field_name,
                        "target_file_path": file_full_path,
                    })
                    if parent_method:
                        edges.append({
                            'edge_type': "USES",
                            "source_type": "METHOD",
                            "source_name": parent_method,
                            "source_file_path": file_full_path,
                            "target_type": "FIELD",
                            "target_name": field_name,
                            "target_file_path": file_full_path,
                        })
                else:
                    global_variable_name = node.child_by_field_name("left").text.decode("utf-8")
                    nodes.append({
                        "type": "GLOBAL_VARIABLE",
                        "name": global_variable_name,
                        "file_path": file_full_path,
                        "code": file_content[node.start_byte:node.end_byte],
                    })
                    edges.append({
                        'edge_type': "CONTAINS",
                        "source_type": "MODULE",
                        "source_name": module_name,
                        "source_file_path": file_full_path,
                        "target_type": "GLOBAL_VARIABLE",
                        "target_name": global_variable_name,
                        "target_file_path": file_full_path,
                    })
                    if parent_function:
                        edges.append({
                            'edge_type': "USES",
                            "source_type": "FUNCTION",
                            "source_name": parent_function,
                            "source_file_path": file_full_path,
                            "target_type": "GLOBAL_VARIABLE",
                            "target_name": global_variable_name,
                            "target_file_path": file_full_path,
                        })

                # TODO: need to find fields used in return statements and other places
                
            for child in node.children:
                traverse(child, parent_class, parent_function, parent_method)

        root_node = tree.root_node
        traverse(root_node)
        
        return nodes, edges

    """def parse_source_file_second_pass(file_path):
        # This function is for the second pass. It sets class INHERITS, and subclass CONTAINS
        file_full_path = utils.get_absolute_path(file_path)
        try:
            lang = filename_to_lang(file_full_path)

            # Read the file content
            with open(file_full_path, 'r', encoding="utf-8") as file:
                file_content = file.read()

            # Initialize tree-sitter parser with language
            parser = get_parser(lang)

            # Parse the file content
            tree = parser.parse(bytes(file_content, "utf8"))

        except Exception:
            # Return None if parsing fails
            print("Error: ", file_full_path)
            return None

        def extract_imports(tree):
            root_node = tree.root_node

            imports = []

            # Traverse the tree to find import nodes
            def traverse(node):
                if node.type == "import_statement":
                    # Handle 'import ...' style imports
                    # Extract imported module names
                    for child in node.children:
                        if child.type == "dotted_name":
                            imports.append(child.text.decode('utf-8'))
                if node.type == "import_from_statement":
                    # Handle 'from module import ...' style imports
                    module_name = node.child_by_field_name("module_name").text.decode('utf-8')
                    imports.append(module_name)

                for child in node.children:
                    traverse(child)

            traverse(root_node)
            return imports
        
        def extract_class(tree):
            # TODO: need to handle full name of class: https://github.com/modelscope/modelscope-agent/blob/master/modelscope_agent/environment/graph_database/ast_search/ast_manage.py#L237

            classes = []

            # Traverse the tree to find import nodes
            def traverse(node):
                if node.type == "class_definition":
                    print(node.text.decode("utf-8"))
                    print(node.children)
                    print(node.child_by_field_name("superclasses"))
                    for child in node.children:
                        print(child.text.decode("utf-8"), child.type)
                    class_name = node.child_by_field_name("name").text.decode('utf-8')

                    # Check for a base class
                    base_class_node = node.child_by_field_name("superclasses")
                    if base_class_node:
                        base_class_name = base_class_node.text.decode('utf-8')
                    else:
                        base_class_name = None

                    classes.append({
                        'class_name': class_name,
                        'base_class': base_class_name
                    })

                for child in node.children:
                    traverse(child)

            root_node = tree.root_node
            traverse(root_node)
            return classes

        def extract_inherited_methods(tree):
            # https://github.com/modelscope/modelscope-agent/blob/master/modelscope_agent/environment/graph_database/ast_search/ast_manage.py#L108
            pass # TODO

        imports = extract_imports(tree)
        classes = extract_class(tree)

        return imports, classes
        """

    @staticmethod
    def parse_directory_first_pass(directory):
        python_files = []
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith(".py"):
                    python_files.append(os.path.join(root, file))
        
        nodes = []
        edges = []
        for py_file in python_files:
            nodes_, edges_ = FileParser.parse_source_file_first_pass(py_file)
            nodes += nodes_
            edges += edges_
        
        return nodes, edges

