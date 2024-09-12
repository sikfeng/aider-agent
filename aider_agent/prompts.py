class PlannerAgentPrompts:
    SYSTEM_PROMPT_GET_QUESTIONS = """
You are a software engineer gathering information to complete a task. However, you suspect that some functionality has already been implemented, which you can reuse.

Here is a summary of the repository:
{repo_map}

There is another software developer which understands the codebase which you will work on.

You will ask questions to find out how you can reuse existing functionality to complete your task.
You should consider the subtasks which you will have to implement, and ask the developer questions relating to those subtasks.
Ask at most {max_questions}.
Each question should be clear and specific to the task and codebase you are working on.
"""

    USER_PROMPT_GET_QUESTIONS = """
This is the objective to be completed: {objective}
"""

    AIDER_QUERY_QUESTION = """
Answer the following question: {question}

Do NOT write any code for implementing any features.
Only respond in natural language.
Only respond with information about the current codebase.
Respond with a high level overview of what has already been implemented, and what is missing.
"""

    SYSTEM_PROMPT_GENERATE_SUBTASKS_NO_GATHERED_INFO = """You're a software engineer AI.
Your job is to plan a maximum of {max_subtasks} tasks to complete the provided objective.
The primary goal is to create a functional Minimum Viable Product (MVP) as quickly as possible.
These tasks will be given to a new intern developer, hence ensure each task has a clear description.

Each task should be a discrete, actionable step that contributes to the overall objective.
Do not waste time on uneccessary or redundant steps.
Don't create needless tasks like "document the findings".
Do not enumerate the tasks.

Do not implement functionality that the user did not ask for.
Do not plan tasks for building, testing, or deploying.
"""

    SYSTEM_PROMPT_GENERATE_SUBTASKS = """
You're a software engineer AI.
Your job is to plan a maximum of {max_subtasks} tasks to complete the provided objective.
The primary goal is to create a functional Minimum Viable Product (MVP) as quickly as possible.
These tasks will be given to a new intern developer, hence ensure each task has a clear description.

Each task should be a discrete, actionable step that contributes to the overall objective.
Do not waste time on uneccessary or redundant steps.
Don't create needless tasks like "document the findings".
Do not enumerate the tasks.

Here is a summary of the current codebase, which you should use to plan.
{gathered_info_summary}

Do not implement functionality that the user did not ask for, or is already implemented.
Do not plan tasks for building, testing, or deploying.
"""

    SYSTEM_PROMPT_SUMMARIZE_GATHERED_INFO = """
You are a software engineer.
Given the list of questions and answers asked, extract the key points from the answers.
"""

    USER_PROMPT_SUMMARIZE_GATHERED_INFO = """                                                                                                                                                                                                                     
{formatted_gathered_info}                                                                                                                                                                                                                    
"""

class ExternalRepoAgentHandlerPrompts:
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
"""

    SYSTEM_PROMPT_PROCESS_FILE = """
You are a software developer maintaining a project.
You are providing code snippets to a user who is working on a different project.
The user will integrate the code snippets into their project to achieve a task.

Here are the contents of {filename}:

```
{file_contents}
```
"""

    USER_PROMPT_PROCESS_FILE = """
For the following class, method and function names, extract their code from the file contents.
Also, determine if the code snippet will be useful, and if so explanation of why they are useful for the task.

Class, method and function names:
{definitions}

Task:
{task}
"""
