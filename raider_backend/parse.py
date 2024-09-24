"""
This module provides functionality to parse source code files and extract
class, method, and function definitions using the tree-sitter library.
"""
from grep_ast import filename_to_lang
from tree_sitter_languages import get_parser

from raider_backend import utils


def get_class_method_function_defs(
        file_full_path: str) -> tuple[dict, dict, list] | None:
    """
    Parses a source code file to extract class, method, and function
    definitions using tree-sitter.

    This function reads the content of a source code file, determines
    its programming language, and uses the tree-sitter library to parse
    the file. It then traverses the syntax tree to extract definitions
    of classes, methods, and functions, and returns them in separate
    dictionaries.

    :param file_full_path: The full path to the source code file to
        be parsed.
    :type file_full_path: str

    :return: A tuple containing three elements:
        - A dictionary where keys are class names and values are
          their definitions.
        - A dictionary where keys are method names and values are
          their definitions.
        - A dictionary where keys are function names and values are
          their definitions.
        Returns (None, None, None) if parsing fails.
    :rtype: tuple[dict, dict, list] | None

    :raises Exception: If there is an error in reading the file or parsing
        its content.
    """

    file_full_path = utils.get_absolute_path(file_full_path)
    # I wish all languages had consistent types from the query, but alas
    # so we have to just test and add each case

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
        return None, None, None

    # Initialize data structures to store parsed information
    class_definitions = {}
    method_definitions = {}
    function_definitions = {}

    file_content_line = file_content.splitlines()

    # TODO: need to decide whether class, functions and methods should be
    # handled the same or differently
    def traverse_node(node):
        if node.grammar_name in ["class_declaration", "class_definition"]:
            class_name = node.child_by_field_name("name").text.decode("utf8")
            class_def = "\n".join(
                file_content_line[node.start_point[0]:node.end_point[0] + 1])
            class_definitions[class_name] = class_def
        elif node.grammar_name in ['function_declaration']:
            function_name = node.child_by_field_name(
                "name").text.decode("utf8")
            function_def = "\n".join(
                file_content_line[node.start_point[0]:node.end_point[0] + 1])
            function_definitions[function_name] = function_def
        elif node.grammar_name in ["method_definition"]:
            method_name = node.child_by_field_name("name").text.decode("utf8")
            method_def = "\n".join(
                file_content_line[node.start_point[0]:node.end_point[0] + 1])
            method_definitions[method_name] = method_def

        for child in node.children:
            traverse_node(child)

    traverse_node(tree.root_node)
    # Return the collected information
    return class_definitions, method_definitions, function_definitions
