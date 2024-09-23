"""
This module defines the PlannerAgent class, which is responsible for
managing the planning process for a given objective. The PlannerAgent
utilizes a language model to gather information, generate questions,
and create a plan consisting of subtasks to achieve the specified
objective.
"""
import asyncio
import logging
import re
from typing import TYPE_CHECKING

from raider_backend import utils
from raider_backend.prompts import PlannerAgentPrompts

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

    async def generate_subtasks(self, objective: str):
        """
        Generate a list of subtasks to achieve the given objective.

        :param objective: The main objective.
        :return: A list of subtasks.
        """
        tmp_model_name = self.model_name
        # Empirically, only these two models have been successful in generating a plan following the format specified.
        if tmp_model_name not in ["azure/gpt-4o", "bedrock/mistral.mistral-large-2407-v1:0"]:
            tmp_model_name = "azure/gpt-4o"

        async def query_codebase(query_message: str) -> str:
            """Ask a Codebase AI assistant questions about the existing codebase
            The assistant can only read the codebase and answer queries. It cannot run commands, execute files, or edit files."""
            self.agent_manager.main_repo_agent.reset()

            response = ""
            for _ in range(3):
                curr_response = ""
                async for response_chunk in self.agent_manager.main_repo_agent.ask(query_message):
                    curr_response += response_chunk
                response += curr_response + "\n\n"
                if self.agent_manager.main_repo_agent.coder.reflected_message is None:
                    break
                query_message = self.agent_manager.main_repo_agent.coder.reflected_message

            return response

        def finetune_codebase_summary_and_plan(shared_variables, additional_info:str):
            """Incorporates additional info to summary of codebase, and finetunes the plan"""
            res = utils.llm(self.model_name)(
                system_prompt="Finetune the codebase summary with additional infoi. The summary should focus on what are the functionality already implemented, and what functionality is not implemented yet",
                user_prompt=(
                    f"**Current summary**: {shared_variables['Summary']} \n\n"
                    f"**Additional info**: {additional_info} \n\n"
                ),
            )
            shared_variables["Summary"] = res

            res = utils.llm(self.model_name)(
                system_prompt="""Finetune the plan using additional info.

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
""",
                user_prompt=(
                    f"**Existing plan**: {shared_variables['Plan']} \n\n"
                    f"**Additional info**: {additional_info} \n\n"
                    f"**Objective**: {objective}"),
            )
            shared_variables["Plan"] = res

        from taskgen import AsyncAgent
        agent = AsyncAgent(
            'Code planner',
            "Help user to plan tasks to ensure that the code fufils a requirement. You should ensure that the shared_variable Plan will implement the user's objective.",
            llm = utils.llm_async(tmp_model_name),
            shared_variables = {"Plan": "", "Summary": ""},
            default_to_llm = False,
            max_subtasks = 10,
            global_context = "Tentative plan: <Plan>, Tentative summary: <Summary>",
        )
        agent.assign_functions(function_list=[query_codebase, finetune_codebase_summary_and_plan])

        agent.reset()
        await agent.run(f"User objective: {objective}")
        
        if agent.shared_variables["Plan"] == "":
            self.logger.warning("Plan is empty")
            yield ["Plan is empty. Either the task was already completed, or an error occurred."]
            return
        
        self.logger.info("Generated plan: %s", agent.shared_variables["Plan"])

        def _parse_tasks(text):
            # Regular expression to match each task and its task type
            task_pattern = re.compile(r'\[Task (\d+)\](.*?)\[TASK TYPE: ([\w\s]+)\]', re.DOTALL)
            
            # Find all matches in the text
            tasks = task_pattern.findall(text)
            
            # Extract tasks and task types
            parsed_tasks = []
            for task in tasks:
                task_number = task[0]
                task_body = task[1].strip()
                task_type = task[2]
                parsed_tasks.append({
                    'task_number': task_number,
                    'task_body': task_body,
                    'task_type': task_type
                })
            
            return parsed_tasks

        # TODO: add a check for number of tasks in agent.shared_variables["Plan"], and match with parsed
        # if not equal, send a llm query to fix formatting

        parsed_tasks = _parse_tasks(agent.shared_variables["Plan"])
        self.logger.info("Parsed tasks: %s", parsed_tasks)
        yield parsed_tasks


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
