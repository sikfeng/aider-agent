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
            "init_repo_agent = aider_agent.repo_agent:main",
            "launch_endpoint = aider_agent.launch:main",
        ],
    },
    description="Autonomous Software Development",
    url="https://github.com/sikfeng/aider-agent",
)
