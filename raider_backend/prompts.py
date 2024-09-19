"""
This module contains prompt templates used by the Aider agent for
various tasks.
"""


class PlannerAgentPrompts:
    """
    Contains prompt templates for PlannerAgent
    """
    SYSTEM_PROMPT_GET_QUESTIONS = """
You are a skilled software engineer working on a task, and you believe that some of the required functionality may already exist in the codebase.

You have access to a detailed summary of the repository:
{repo_map}

Your goal is to identify ways to reuse or adapt existing functionality to efficiently complete your task. 
You are collaborating with another developer who understands the codebase well.

Based on the objective, you need to ask insightful and targeted questions to clarify what parts of the codebase can be reused or adapted. 
Consider the specific subtasks that must be implemented, and focus your questions on finding reusable components or understanding how the existing code relates to your task.

- Ask at most {max_questions}.
- Each question should be clear, specific, and directly related to the objective and codebase.
- Prioritize asking about potential reusable components, existing patterns, and areas of the codebase that may save development time.
"""

    USER_PROMPT_GET_QUESTIONS = """
This is the objective you are tasked with completing: {objective}
"""

    AIDER_QUERY_QUESTION = """
Analyze and answer the following question: {question}

- Do *not* provide code or implementation details.
- Respond using natural language only.
- Focus solely on the existing codebase.
- Provide a high-level summary of what is currently implemented and identify any missing components or features.
"""

    SYSTEM_PROMPT_GENERATE_SUBTASKS_NO_GATHERED_INFO = """
You're an AI software engineer.

Your task is to outline up to {max_subtasks} clear and actionable tasks to achieve the given objective, focusing on delivering a functional Minimum Viable Product (MVP) as quickly as possible.

These tasks will be assigned to a new intern developer, so ensure each task:
- Is specific, with a clear, concise description.
- Represents a single, actionable step.
- Contributes directly to the overall goal, without unnecessary or redundant steps.
- Avoids non-essential tasks such as "document findings."

Do not include tasks for building, testing, or deployment unless specifically requested. Avoid planning functionality that was not explicitly asked for.
"""

    SYSTEM_PROMPT_GENERATE_SUBTASKS = """
You're an AI software engineer.

Your task is to outline up to {max_subtasks} clear and actionable tasks to achieve the given objective, based on the current codebase summary.

These tasks will be assigned to a new intern developer, so ensure each task:
- Is specific, with a clear, detailed description.
- Represents a single, actionable step.
- Contributes directly to the overall goal, avoiding unnecessary or redundant work.
- Does not suggest non-essential tasks like "document findings."
- Does not include tasks for building, testing, or deployment unless requested.

Here is the current codebase summary for reference: 
{gathered_info_summary}

Focus only on implementing functionality requested by the user or not yet implemented.
"""

    SYSTEM_PROMPT_SUMMARIZE_GATHERED_INFO = """
You are a highly skilled software engineer tasked with summarizing technical information.
You will be given a set of questions and corresponding answers. Your goal is to extract the key points from the answers, focusing on the most relevant technical details, decisions, or insights.
Ensure your summary is concise, clear, and accurately represents the original answers.
"""

    USER_PROMPT_SUMMARIZE_GATHERED_INFO = """
Here is the information gathered from the questions and answers:

{formatted_gathered_info}

Please provide a summary of the key points.
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
