import re
from pathlib import Path

from setuptools import find_packages, setup

def get_requirements(suffix=""):
    if suffix:
        fname = "requirements-" + suffix + ".txt"
        fname = Path("requirements") / fname
    else:
        fname = Path("requirements.txt")

    requirements = fname.read_text().splitlines()

    return requirements


requirements = get_requirements()

setup(
    name="aider_agent",
    version="0.0.1",
    install_requires=requirements,
    python_requires=">=3.9,<3.13",
    entry_points={
        "console_scripts": [
            "init_aider_agent = aider_agent.aider_agent:main",
            "aider_agent_manager = aider_agent.manager:main",
        ],
    },
    description="badly written code :sadge",
    url="https://github.com/sikfeng/aider-agent",
)