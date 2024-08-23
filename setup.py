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

packages = find_packages()

setup(
    name="aider_agent",
    version="0.0.1",
    install_requires=requirements,
    python_requires=">=3.9,<3.13",
    package_dir={"aider_agent": "aider_agent"},
    entry_points={
        "console_scripts": [
            "init_aider_process = aider_agent.aider_process:main",
            "aider_agent_manager = aider_agent.manager:main",
        ],
    },
    description="software dev agents with aider",
    url="https://github.com/sikfeng/aider-agent",
)