"""
Utility functions for the Aider Agent.

This module provides various utility functions to support the
operations of the Aider Agent. It includes functions for path
manipulation, synchronous and asynchronous LLM completion, and retry
mechanisms for strict JSON parsing.
"""
import asyncio
import datetime
from functools import partial
from pathlib import Path
import tempfile

import litellm
from litellm import acompletion, completion
from strictjson import strict_json, strict_json_async

litellm.suppress_debug_info = True
litellm.set_verbose = True
litellm.drop_params = True


def get_tmp_file(name: str) -> str:
    """
    Generate a temporary file path.

    :param name: The name of the temporary file.
    :return: The temporary file path.
    """
    (Path(tempfile.gettempdir()) / "raider_backend").mkdir(parents=True, exist_ok=True)
    return str(Path(tempfile.gettempdir()) / "raider_backend" / f"{name}_{datetime.datetime.now().strftime('%Y-%m-%d %Hh%Mm%Ss')}.log")


def get_absolute_path(path: str) -> str:
    """
    Convert a given path to its absolute form.

    :param path: The path to convert.
    :return: The absolute path as a string.
    """
    path_obj = Path(path)

    if not path_obj.is_absolute():
        path_obj = path_obj.resolve()

    return str(path_obj)


def llm(model_name: str) -> partial:
    """
    Create a partial function for synchronous LLM completion.

    :param model_name: The name of the model to use.
    :return: A partial function for LLM completion.
    """
    return partial(_llm, model_name=model_name)


def llm_async(model_name: str) -> partial:
    """
    Create a partial function for asynchronous LLM completion.

    :param model_name: The name of the model to use.
    :return: A partial function for asynchronous LLM completion.
    """
    return partial(_llm_async, model_name=model_name)


def _llm(model_name: str, system_prompt: str, user_prompt: str) -> str:
    """
    Generate a response using the LLM.

    :param model_name: The name of the model to use.
    :param system_prompt: The system prompt.
    :param user_prompt: The user prompt.
    :return: The response from the LLM.
    """
    response = completion(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )
    return response.choices[0].message.content


async def _llm_async(
        model_name: str,
        system_prompt: str,
        user_prompt: str) -> str:
    """
    Generate a response using the LLM asynchronously.

    :param model_name: The name of the model to use.
    :param system_prompt: The system prompt.
    :param user_prompt: The user prompt.
    :return: The response from the LLM.
    """
    response = await acompletion(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )
    return response.choices[0].message.content


async def strict_json_retry(
        system_prompt: str,
        user_prompt: str,
        output_format: dict,
        llm,
        max_retries: int = 5,
        retry_delay: int = 10) -> dict:
    """
    Call strict_json with retries on RateLimitError.

    :param system_prompt: The system prompt.
    :param user_prompt: The user prompt.
    :param output_format: The expected output format.
    :param llm: The LLM to use.
    :param max_retries: Maximum number of retries.
    :param retry_delay: Delay between retries in seconds.
    :return: The response from strict_json.
    """
    for _ in range(max_retries):
        try:
            return strict_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                output_format=output_format,
                llm=llm
            )
        except litellm.exceptions.RateLimitError:
            await asyncio.sleep(retry_delay)
    raise RuntimeError("Max retries exceeded for strict_json")


async def strict_json_async_retry(
        system_prompt: str,
        user_prompt: str,
        output_format: dict,
        llm,
        max_retries: int = 5,
        retry_delay: int = 10) -> dict:
    """
    Call strict_json with retries on RateLimitError.

    :param system_prompt: The system prompt.
    :param user_prompt: The user prompt.
    :param output_format: The expected output format.
    :param llm: The LLM to use.
    :param max_retries: Maximum number of retries.
    :param retry_delay: Delay between retries in seconds.
    :return: The response from strict_json.
    """
    for _ in range(max_retries):
        try:
            return await strict_json_async(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                output_format=output_format,
                llm=llm
            )
        except litellm.exceptions.RateLimitError:
            await asyncio.sleep(retry_delay)
    raise RuntimeError("Max retries exceeded for strict_json_async")
