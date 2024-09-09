from .main_repo_agent import MainRepoAgent

import logging
import asyncio
from strictjson import strict_json
from . import utils


class PlannerAgent:
    """
    A class to manage the Planner agent.
    """

    def __init__(
            self,
            model_name: str = "azure/gpt-4o",
            map_tokens=8092,
            max_questions=5,
            max_subtasks=5,
            max_concurrent_llm_queries=1,
            max_reflections: int = 5) -> None:
        """
        Initialize the PlannerAgent.

        :param model_name: The name of the model to use.
        """
        self.model_name = model_name
        self.logger = logging.getLogger("PlannerAgent")
        self.map_tokens = map_tokens

        self.max_questions = max_questions
        self.max_subtasks = max_subtasks
        self.max_concurrent_llm_queries = max_concurrent_llm_queries
        self.max_reflections = max_reflections

        return

    async def gather_information(self, objective: str) -> dict:
        """
        Gather necessary information to generate a plan for the given objective.

        :param objective: The main objective.
        :return: A dictionary containing the gathered information.
        """
        # TODO: this is very messy instantiating multiple MainRepoAgents, can it be cleaner?
        # TODO: handle case where repo is empty => repo map is empty
        main_repo_agent = MainRepoAgent(model_name=self.model_name)
        repo_map = main_repo_agent.get_repo_map()
        del main_repo_agent

        self.logger.info("Repo Map: %s", repo_map)
        # if the git repo has no files, repo_map is None
        # not sure if there is a case where repo_map may be just whitespace but I handle it as the same
        if repo_map is None or repo_map.strip() == "":
            return None

        # Ask the LLM what questions to ask using strictjson
        system_prompt = """
You are a software engineer gathering information to complete a task. However, you suspect that some functionality has already been implemented, which you can reuse.

Here is a summary of the repository:
{repo_map}

There is another software developer which understands the codebase which you will work on.

You will ask questions to find out how you can reuse existing functionality to complete your task.
You should consider the subtasks which you will have to implement, and ask the developer questions relating to those subtasks.
Ask at most {max_questions}.
Each question should be clear and specific to the task and codebase you are working on.
"""
        system_prompt = system_prompt.format(
            repo_map=repo_map, max_questions=self.max_questions)
        user_prompt = """
This is the objective to be completed: {objective}
"""
        user_prompt = user_prompt.format(
            max_questions=self.max_questions,
            objective=objective)
        questions_response = strict_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_format={
                'questions': 'Array of strings which are questions to ask, type: Array[str]'},
            llm=utils.llm(
                self.model_name))

        questions = questions_response['questions']
        self.logger.info("Questions: %s", questions)

        async def ask_aider(question: str) -> str:
            main_repo_agent = MainRepoAgent(model_name=self.model_name)
            query_message = f"""Answer the following question: {question}

Do NOT write any code for implementing any features.
Only respond in natural language.
Only respond with information about the current codebase.
Respond with a high level overview of what has already been implemented, and what is missing.
"""
            response = ""
            # TODO: make the max reflections a class variable
            for _ in range(self.max_reflections):
                curr_response = ""
                async for response_chunk in main_repo_agent.ask(query_message):
                    curr_response += response_chunk
                response += curr_response + "\n"
                if main_repo_agent.coder.reflected_message is None:
                    break
                else:
                    query_message = main_repo_agent.coder.reflected_message
            return question, response

        async def limited_ask_aider(semaphore, question):
            async with semaphore:
                return await asyncio.to_thread(ask_aider, question)

        semaphore = asyncio.Semaphore(self.max_concurrent_llm_queries)

        gathered_info = []
        tasks = [limited_ask_aider(semaphore, question)
                 for question in questions]
        responses = await asyncio.gather(*tasks)
        responses = await asyncio.gather(*responses)

        for question, response in responses:
            gathered_info.append((question, response))

        # Format gathered_info in markdown
        formatted_gathered_info = ""

        for question, answer in gathered_info:
            formatted_gathered_info += """**Question:**
{question}

**Answer:**
{answer}
""".format(question=question, answer=answer)
        self.logger.info("Gathered Information: %s", formatted_gathered_info)

        # Summarize the gathered information
        summary_prompt = """
{formatted_gathered_info}
"""
        summary_prompt = summary_prompt.format(
            formatted_gathered_info=formatted_gathered_info)
        summary_response = utils.llm(
            self.model_name)(
            system_prompt="""You are a software engineer. Given the list of questions and answers asked, extract the key points from the answers""",
            user_prompt=f"{formatted_gathered_info}")
        self.logger.info("Summary: %s", summary_response)
        return summary_response

    async def generate_subtasks(self, objective: str) -> list[str]:
        """
        Generate a list of subtasks to achieve the given objective.

        :param objective: The main objective.
        :return: A list of subtasks.
        """
        '''# Restate the problem statement
        system_msg = """You are a requirements analyst.
Restate the following as an instruction for a software developer
"""
        user_msg = objective
        objective = utils.llm(self.model_name)(
            system_prompt=system_msg, user_prompt=user_msg
        )'''

        # Gather necessary information
        gathered_info_summary = await self.gather_information(objective)
        if gathered_info_summary is None:
            system_msg = """You're a software engineer AI.
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
        else:
            system_msg = """You're a software engineer AI.
Your job is to plan a maximum of {max_subtasks} tasks to complete the provided objective.
The primary goal is to create a functional Minimum Viable Product (MVP) as quickly as possible.
These tasks will be given to a new intern developer, hence ensure each task has a clear description.

Each task should be a discrete, actionable step that contributes to the overall objective.
Do not waste time on uneccessary or redundant steps.
Don't create needless tasks like "document the findings".
Do not enumerate the tasks.

Here is a summary of the current codebase, which you should use to plan.
{gathered_info}

Do not implement functionality that the user did not ask for, or is already implemented.
Do not plan tasks for building, testing, or deploying.
    """

        system_msg = system_msg.format(
            max_subtasks=self.max_subtasks,
            gathered_info=gathered_info_summary)
        # print(system_msg)

        res = strict_json(
            system_prompt=system_msg,
            user_prompt=f"Objective: {objective}",
            output_format={'Plan': 'Array of subtasks, type: Array[str]'},
            llm=utils.llm(self.model_name)
        )

        return res['Plan']

    def finetune_subtasks(self, objective: str, instruction: str) -> list[str]:
        """
        Finetune the generated subtasks based on additional instructions.

        :param objective: The main objective.
        :param instruction: Additional instructions for finetuning.
        :return: A list of finetuned subtasks.
        """
        # TODO
        return []
