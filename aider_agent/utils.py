from functools import partial

from pathlib import Path

import litellm
from litellm import acompletion, completion

litellm.suppress_debug_info = True
litellm.set_verbose = True
litellm.drop_params = True


def get_absolute_path(path):
    # Create a Path object
    path_obj = Path(path)

    # Check if the path is already absolute
    if not path_obj.is_absolute():
        path_obj = path_obj.resolve()

    return str(path_obj)

def llm(model_name:str):
    return partial(_llm, model_name=model_name)

def _llm(model_name:str, system_prompt: str, user_prompt: str) -> str:
    """
    Generate a response using the LLM.

    :param system_prompt: The system prompt.
    :param user_prompt: The user prompt.
    :return: The response from the LLM.
    """
    
    # define your own LLM here
    response = completion(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )
    return response.choices[0].message.content

async def llm_async(model_name: str, system_prompt: str, user_prompt: str) -> str:
    """
    Generate a response using the LLM.

    :param system_prompt: The system prompt.
    :param user_prompt: The user prompt.
    :return: The response from the LLM.
    """
    
    # define your own LLM here
    response = await acompletion(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )
    return response