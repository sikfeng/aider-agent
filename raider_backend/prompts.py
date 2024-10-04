"""
This module contains prompt templates used by the Aider agent for
various tasks.
"""


class PlannerAgentPrompts:
    """
    Contains prompt templates for PlannerAgent
    """
    SYSTEM_PROMPT_FINETUNE_CODEBASE_SUMMARY = """
Finetune the codebase summary with additional info. The summary should focus on what are the functionality already implemented, and what functionality is not implemented yet. Respond in English.
"""

    USER_PROMPT_FINETUNE_CODEBASE_SUMMARY = """
**Current Summary**: {summary}

**Additional info**: {additional_info}
"""

    SYSTEM_PROMPT_FINETUNE_PLAN = """
Finetune the plan using additional info. Respond in English.

Ensure each task:
- Is specific, with a clear, detailed description.
- Represents a single, actionable step.
- Contributes directly to the overall goal, avoiding unnecessary or redundant work.
- Does not suggest non-essential tasks like "document findings."
- Does not include tasks for building, testing, or deployment unless requested.

Output Format:
---------------

[Task 1]

<description of task>

[TASK TYPE: <type of task: Enum['Coding', 'Command execution', 'User action']> ]

[Task 2]

<description of task>

[TASK TYPE: <type of task: Enum['Coding', 'Command execution', 'User action']> ]

...

[Task N]

<description of task>

[TASK TYPE: <type of task: Enum['Coding', 'Command execution', 'User action']> ]
"""

    USER_PROMPT_FINETUNE_PLAN = """
**Existing plan**: {plan}

**Additional info**: {additional_info}

**Objective**: {objective}
"""


class ExternalRepoAgentHandlerPrompts:
    """
    Contains prompt templates for ExternalRepoAgentHandlerPrompts
    """
    SYSTEM_PROMPT_FIND_RELEVANT_FILENAMES = """
You are a software developer maintaining a project.
You are providing code snippets to a user who is working on a different project.
The user will integrate the code snippets into their project to achieve a task.

Here are summaries of some files present in your project.

{repo_map}
"""

    USER_PROMPT_FIND_RELEVANT_FILENAMES = """
Please look through the repository structure and suggest a list of files that is relevant to the following task.

{task}

Please only provide the full path and return at most 5 files.
"""

    SYSTEM_PROMPT_FIND_RELEVANT_DEFINITIONS = """
You are a software developer maintaining a project.
You are providing code snippets to a user who is working on a different project.
The user will integrate the code snippets into their project to achieve a task.

Here are summaries of some files present in your project.

{repo_map}
"""

    USER_PROMPT_FIND_RELEVANT_DEFINITIONS = """
Here are the files which the contain relevant code snippets.

{filenames}

For each of the above files, look through the repository structure to suggest the relevant class or functions that can be used for the following task.

{task}

Only provide the class or function names, do not include the decorators such as "class ClassName", "def FunctionName", function FunctionName" etc.
"""

    SYSTEM_PROMPT_PROCESS_FILE_FOR_DEFINITIONS = """
You are a software developer maintaining a project.
You are providing code snippets to a user who is working on a different project.
The user will integrate the code snippets into their project to achieve a task.
Here are some class, method or function names with their definitions

{formatted_defs}

Determine which ones may be useful for our task, as well as an explanation of why they may be useful.
"""

    USER_PROMPT_PROCESS_FILE_FOR_DEFINITIONS = """
Task:
{task}
"""

class MainRepoAgentPrompts:
    """
    Contains prompt templates for MainRepoAgent
    """
    SYSTEM_PROMPT_GENERATE_SHELL_CMD = """
Provide only {shell} commands for {os} without any description.
If there is a lack of details, provide most logical solution.
Ensure the output is a valid shell command.
If multiple steps required try to combine them together using &&.
Provide only plain text without Markdown formatting.
Do not provide markdown formatting such as ```.
"""

    USER_PROMPT_GENERATE_SHELL_CMD = """
{subtask}
"""