from functools import partial

from pathlib import Path

import litellm
from litellm import acompletion, completion

litellm.suppress_debug_info = True
litellm.set_verbose = True
litellm.drop_params = True


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
