"""
This module defines the PlannerAgent class, which is responsible for
managing the planning process for a given objective. The PlannerAgent
utilizes a language model to gather information, generate questions,
and create a plan consisting of subtasks to achieve the specified
objective.
"""
import logging
import asyncio

from . import utils
from .repo_agent import MainRepoAgent
from .prompts import PlannerAgentPrompts


class PlannerAgent:
    """
    A class to manage the Planner agent.
    """

    def __init__(
            self,
            model_name: str = "openai/gpt-4o",
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

    async def gather_information(self, objective: str) -> dict:
        """
        Gather necessary information to generate a plan for the given
        objective.

        :param objective: The main objective.
        :return: A dictionary containing the gathered information.
        """
        # TODO: this is very messy instantiating multiple
        # MainRepoAgents, can it be cleaner?
        main_repo_agent = MainRepoAgent(model_name=self.model_name)
        repo_map = main_repo_agent.get_repo_map()
        del main_repo_agent

        self.logger.info("Repo Map: %s", repo_map)
        # if the git repo has no files, repo_map is None
        # not sure if there is a case where repo_map may be just
        # whitespace but I handle it as the same
        if repo_map is None or repo_map.strip() == "":
            return None

        # Ask the LLM what questions to ask using strictjson
        system_prompt = PlannerAgentPrompts.SYSTEM_PROMPT_GET_QUESTIONS.format(
            repo_map=repo_map, max_questions=self.max_questions)
        user_prompt = PlannerAgentPrompts.USER_PROMPT_GET_QUESTIONS.format(
            objective=objective)
        questions_response = await utils.strict_json_retry(
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
            query_message = PlannerAgentPrompts.AIDER_QUERY_QUESTION.format(
                question=question)
            response = ""
            for _ in range(self.max_reflections):
                curr_response = ""
                for response_chunk in main_repo_agent.ask(query_message):
                    curr_response += response_chunk
                response += curr_response + "\n"
                if main_repo_agent.coder.reflected_message is None:
                    break
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
            formatted_gathered_info += f"""**Question:**
{question}

**Answer:**
{answer}
"""
        self.logger.info("Gathered Information: %s", formatted_gathered_info)

        # Summarize the gathered information
        system_prompt = PlannerAgentPrompts.SYSTEM_PROMPT_SUMMARIZE_GATHERED_INFO
        user_prompt = PlannerAgentPrompts.USER_PROMPT_SUMMARIZE_GATHERED_INFO.format(
            formatted_gathered_info=formatted_gathered_info)
        summary_response = utils.llm(
            self.model_name)(
            system_prompt=system_prompt,
            user_prompt=user_prompt)
        self.logger.info("Summary: %s", summary_response)
        return summary_response

    async def generate_subtasks(self, objective: str) -> list[str]:
        """
        Generate a list of subtasks to achieve the given objective.

        :param objective: The main objective.
        :return: A list of subtasks.
        """
        '''
        # Restate the problem statement
        system_prompt = """You are a requirements analyst.
Restate the following as an instruction for a software developer
"""
        user_prompt = objective
        objective = utils.llm(self.model_name)(
            system_prompt=system_prompt, user_prompt=user_prompt
        )
        '''

        # Gather necessary information
        gathered_info_summary = await self.gather_information(objective)
        if gathered_info_summary is None:
            system_prompt = PlannerAgentPrompts.SYSTEM_PROMPT_GENERATE_SUBTASKS_NO_GATHERED_INFO.format(
                max_subtasks=self.max_subtasks, gathered_info_summary=gathered_info_summary)
        else:
            system_prompt = PlannerAgentPrompts.SYSTEM_PROMPT_GENERATE_SUBTASKS.format(
                max_subtasks=self.max_subtasks, gathered_info_summary=gathered_info_summary)

        res = await utils.strict_json_retry(
            system_prompt=system_prompt,
            user_prompt=f"Objective: {objective}",
            output_format={'Plan': 'Array of subtasks, type: Array[str]'},
            llm=utils.llm(self.model_name)
        )

        return res['Plan']

    def finetune_subtasks(self, objective: str, instruction: str) -> list[str]:
        """
        Finetune the generated subtasks based on additional
        instructions.

        :param objective: The main objective.
        :param instruction: Additional instructions for finetuning.
        :return: A list of finetuned subtasks.
        """
        # TODO
        return []
