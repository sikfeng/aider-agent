from aider.coders import Coder
from aider.models import Model
from aider.io import InputOutput

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
            max_concurrent_llm_queries=2) -> None:
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
        return

    async def gather_information(self, objective: str) -> dict:
        """
        Gather necessary information to generate a plan for the given objective.

        :param objective: The main objective.
        :return: A dictionary containing the gathered information.
        """
        # Ask the LLM what questions to ask using strictjson
        system_prompt = """
You are a software engineer gathering information to complete a task. However, you suspect that some functionality has already been implemented, which you can reuse.

There is another software developer which understands the codebase which you will work on.

You will ask questions to find out how you can reuse existing functionality to complete your task.
You should consider the subtasks which you will have to implement, and ask the developer questions relating to those subtasks.
"""
        user_prompt = """
What information do you need to know to complete the following task? Give at most {max_questions} questions.
Each question should be clear and specific to the task and codebase you are working on.

{objective}
"""
        user_prompt = user_prompt.format(
            max_questions=self.max_questions,
            objective=objective)
        questions_response = strict_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_format={
                'questions': 'Array of questions, type: Array[str]'},
            llm=utils.llm(
                self.model_name))

        questions = questions_response['questions']
        self.logger.info("Questions: %s", questions)

        def ask_aider(question: str) -> str:
            model = Model(self.model_name)
            io = InputOutput(
                pretty=False,
                yes=True,
            )
            coder = Coder.create(
                main_model=model,
                io=io,
                suggest_shell_commands=False,
                edit_format="ask",
                map_tokens=self.map_tokens,
            )
            coder.run(
                """What files do you need to answer the following question?
{question}
""".format(
                    question=question))
            coder.done_messages = []
            coder.cur_messages = []
            response = coder.run("""Answer the following question: {question}

Do NOT write any code for implementing any features.
Only respond in natural language.
Only respond with information about the current codebase.
Respond with a high level overview of what has already been implemented, and what is missing.
""")
            return question, response

        async def limited_ask_aider(semaphore, question):
            async with semaphore:
                return await asyncio.to_thread(ask_aider, question)

        semaphore = asyncio.Semaphore(self.max_concurrent_llm_queries)

        gathered_info = {}
        tasks = [limited_ask_aider(semaphore, question)
                 for question in questions]
        responses = await asyncio.gather(*tasks)

        for question, response in responses:
            gathered_info[question] = response

        # print(gathered_info)
        return gathered_info

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

        system_msg = """You're a software engineer AI.
Your job is to plan a maximum of {max_subtasks} tasks to complete the provided objective.
The primary goal is to create a functional Minimum Viable Product (MVP) as quickly as possible.
These tasks will be given to a new intern developer, hence ensure each task has a clear description.

Each task should be a discrete, actionable step that contributes to the overall objective.
Do not waste time on uneccessary or redundant steps.
Don't create needless tasks like "document the findings".
Do not enumerate the tasks.

Here are some questions and answers regarding the codebase, which you should use to plan.
{gathered_info}

Do not implement functionality that the user did not ask for, or is already implemented.
Do not plan tasks for building, testing, or deploying.
"""

        # Gather necessary information
        gathered_info = await self.gather_information(objective)

        # Format gathered_info in markdown
        formatted_gathered_info = ""

        for question, answer in gathered_info.items():
            formatted_gathered_info += """**Question:**
{question}

**Answer:**
{answer}
""".format(question=question, answer=answer)

        system_msg = system_msg.format(
            max_subtasks=self.max_subtasks,
            gathered_info=formatted_gathered_info)
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
