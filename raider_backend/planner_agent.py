"""
This module defines the PlannerAgent class, which is responsible for
managing the planning process for a given objective. The PlannerAgent
utilizes a language model to generate a plan consisting of subtasks
to achieve the specified objective.

The PlannerAgent can query the codebase, incorporate additional information,
and generate a structured plan with task types and descriptions.
"""
import logging
import re
from typing import AsyncGenerator, List, Dict, TYPE_CHECKING

from taskgen import Agent

from raider_backend import utils
from raider_backend.prompts import PlannerAgentPrompts

if TYPE_CHECKING:
    from raider_backend.agent_manager import AgentManager


class PlannerAgent:
    """
    A class to manage the Planner agent, responsible for generating subtasks
    to achieve a given objective using language models.
    """

    def __init__(
            self,
            model_name: str = "azure/gpt-4o",
            map_tokens: int = 8092,
            max_iterations: int = 10,
            max_reflections: int = 5,
            agent_manager: 'AgentManager' = None) -> None:
        """
        Initialize the PlannerAgent.

        :param model_name: The name of the model to use.
        :param map_tokens: The number of tokens for mapping.
        :param max_iterations: The maximum number of iterations to run the TaskGen agent.
        :param max_reflections: The maximum number of reflections for MainRepoAgent.
        :param agent_manager: The AgentManager instance.
        """
        self.model_name: str = model_name
        self.logger = logging.getLogger(self.__class__.__name__)
        self.map_tokens: int = map_tokens
        self.agent_manager: 'AgentManager' = agent_manager
        self.max_iterations: int = max_iterations
        self.max_reflections: int = max_reflections

    async def generate_subtasks(self, objective: str) -> AsyncGenerator[List[Dict[str, str]], None]:
        """
        Generate a list of subtasks to achieve the given objective.

        :param objective: The main objective.
        :return: An asynchronous generator yielding lists of parsed tasks.
        :yields: Dict containing either 'info', 'warning', or 'result' keys with corresponding values.
        """
        tmp_model_name = self.model_name
        # Empirically, only these two models have been successful in generating a plan following the format specified.
        if tmp_model_name not in ["azure/gpt-4o", "bedrock/mistral.mistral-large-2407-v1:0"]:
            tmp_model_name = "azure/gpt-4o"

        def query_codebase(query_message: str) -> str:
            """
            Ask a Codebase AI assistant questions about the existing codebase.
            The assistant can only read the codebase and answer queries.
            It cannot run commands, execute files, or edit files.
            It has no memory of previous conversations.

            :param query_message: The question to ask the AI assistant.
            :return: The response from the AI assistant.
            """
            self.agent_manager.main_repo_agent.reset()

            response = ""
            for _ in range(self.max_reflections):
                curr_response = ""
                for response_chunk in self.agent_manager.main_repo_agent.ask(query_message + "\n\nPlease respond in English."):
                    curr_response += response_chunk
                response += curr_response + "\n\n"
                if self.agent_manager.main_repo_agent.coder.reflected_message is None:
                    break
                query_message = self.agent_manager.main_repo_agent.coder.reflected_message

            return response

        def finetune_codebase_summary_and_plan(shared_variables, additional_info:str):
            """
            Incorporates additional info to summary of codebase, and finetunes the plan.
            Additional info should contain information about what has already been implemented, and what is not implemented yet.
            Try to use specific instructions in `additional_info` to finetune the plan.

            :param shared_variables: A dictionary containing 'Summary' and 'Plan' keys.
            :param additional_info: Additional information to incorporate into the summary and plan.
            """
            system_prompt = PlannerAgentPrompts.SYSTEM_PROMPT_FINETUNE_CODEBASE_SUMMARY
            user_prompt = PlannerAgentPrompts.USER_PROMPT_FINETUNE_CODEBASE_SUMMARY.format(summary=shared_variables["Summary"], additional_info=additional_info)
            res = utils.llm(self.model_name)(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            shared_variables["Summary"] = res

            system_prompt = PlannerAgentPrompts.SYSTEM_PROMPT_FINETUNE_PLAN
            user_prompt = PlannerAgentPrompts.USER_PROMPT_FINETUNE_PLAN.format(plan=shared_variables["Plan"], additional_info=additional_info, objective=objective)
            finetuned_plan = utils.llm(self.model_name)(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            shared_variables["Plan"] = finetuned_plan

        agent = Agent(
            "Code planner",
            """
            Plan a list of tasks to fufil the user's objective.
            Avoid reimplementing existing functionality.
            When files need to be edited, find out the filenames that need to be edited and include them in the plan.
            """,
            llm = utils.llm(tmp_model_name),
            shared_variables = {"Plan": "", "Summary": ""},
            default_to_llm = False,
            max_subtasks = self.max_iterations,
            global_context = "Tentative plan: <Plan>, Tentative summary: <Summary>",
        )
        agent.assign_functions(function_list=[query_codebase, finetune_codebase_summary_and_plan])

        agent.reset()
        for _ in range(agent.max_subtasks):
            if agent.task_completed:
                break
            agent.run(f"User objective: {objective}", num_subtasks=1)
            if agent.shared_variables["Plan"]:
                self.logger.info("Tentative plan: %s", agent.shared_variables["Plan"])
                yield {"info": {"Tentative plan": agent.shared_variables["Plan"]}}
            else:
                self.logger.info("No tentative plan yet.")
                yield {"info": {"Tentative plan": "No tentative plan yet."}}
        else:
            self.logger.warning("Planner exceeded maximum iterations.")
        
        if not agent.shared_variables["Plan"]:
            yield {"warning": {"Plan": "Plan was empty. An error may have occurred. Forcefully generating a plan based on agent conversation history."}}
            system_prompt = PlannerAgentPrompts.SYSTEM_PROMPT_FINETUNE_PLAN
            user_prompt = f"""Objective: {objective}

Conversation history:
{agent.subtasks_completed}
"""
            finetuned_plan = utils.llm(self.model_name)(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            agent.shared_variables["Plan"] = finetuned_plan

        self.logger.info("Generated plan: %s", agent.shared_variables["Plan"])

        def _parse_tasks(text):
            """
            Parse the generated plan text into a list of tasks.

            :param text: The plan text to parse.
            :return: A list of dictionaries containing 'task_body' and 'task_type' for each task.
            """
            # Regular expression to match each task and its task type
            task_pattern = re.compile(r'\[Task (\d+)\](.*?)\[TASK TYPE: ([\w\s]+)\]', re.DOTALL)
            
            # Find all matches in the text
            tasks = task_pattern.findall(text)
            
            # Extract tasks and task types
            parsed_tasks = []
            for task in tasks:
                task_body = task[1].strip()
                task_type = task[2].strip() # TODO: what if the LLM didn't return the task type in the exact format I specified? Might need to do edit distance matching
                parsed_tasks.append({
                    'task_body': task_body,
                    'task_type': task_type
                })
            
            return parsed_tasks

        # TODO: add a check for number of tasks in agent.shared_variables["Plan"], and match with parsed
        # if not equal, send a llm query to fix formatting

        parsed_tasks = _parse_tasks(agent.shared_variables["Plan"])
        self.logger.info("Parsed tasks: %s", parsed_tasks)
        yield {"result": parsed_tasks}

    # TODO: refactor agent to be a class field rather than a method variable
    # TODO: add a method to force a plan to be generated based on current conversation history
    # TODO: add a agent reset method
    # TODO: update agent manager with these new methods

    def finetune_subtasks(self, objective: str, instruction: str) -> list[str]:
        """
        Finetune the generated subtasks based on additional
        instructions.

        Note: This method is currently not implemented.

        :param objective: The main objective.
        :param instruction: Additional instructions for finetuning.
        :return: A list of finetuned subtasks.
        """
        # TODO: Implement this method
        return []
