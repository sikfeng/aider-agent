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
from .prompts import PlannerAgentPrompts
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from raider_backend.agent_manager import AgentManager


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
            max_reflections: int = 5,
            agent_manager: 'AgentManager' = None) -> None:
        """
        Initialize the PlannerAgent.

        :param model_name: The name of the model to use.
        :param agent_manager: The AgentManager instance.
        """
        self.model_name = model_name
        self.logger = logging.getLogger("PlannerAgent")
        self.map_tokens = map_tokens
        self.agent_manager: 'AgentManager' = agent_manager

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
        repo_map = self.agent_manager.main_repo_agent.get_repo_map()

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
                'questions': 'Array of strings which are questions to ask, type: Array[str]'
            },
            llm=utils.llm(self.model_name))

        questions = questions_response['questions']
        self.logger.info("Questions: %s", questions)

        async def ask_aider(question: str) -> str:
            query_message = PlannerAgentPrompts.AIDER_QUERY_QUESTION.format(
                question=question)
            response = ""
            for _ in range(self.max_reflections):
                curr_response = ""
                async for response_chunk in self.agent_manager.main_repo_agent.ask(query_message):
                    curr_response += response_chunk
                response += curr_response + "\n"
                if self.agent_manager.main_repo_agent.coder.reflected_message is None:
                    break
                query_message = self.agent_manager.main_repo_agent.coder.reflected_message
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

        for qn_idx, (question, answer) in enumerate(gathered_info):
            formatted_gathered_info += f"""
# Question {qn_idx + 1}
**Question**: {question}
**Answer**: {answer}

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
        # Restate the problem statement
        system_prompt = """
You are a requirements analyst tasked with converting objectives into clear, actionable instructions for a software developer.
Your instructions should be specific, technically accurate, and detailed enough for implementation. 
Ensure to outline any necessary steps, constraints, and considerations for the development process.
"""
        user_prompt = """{objective}"""
        user_prompt = user_prompt.format(objective=objective)
        objective = utils.llm(self.model_name)(
            system_prompt=system_prompt, user_prompt=user_prompt
        )
        self.logger.info("Restated objective: %s", objective)

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
