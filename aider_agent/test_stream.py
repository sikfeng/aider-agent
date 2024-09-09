import httpx
import json

def test_post_endpoint(url, data=None):
    response = ""

    with httpx.stream("POST", url, json=data, timeout=10000.0) as response_stream:
        for partial_response in response_stream.iter_text(chunk_size=200):
            print(partial_response, end='')
            response += partial_response
    print()
    return response

def test_get_endpoint(url):
    response = ""

    with httpx.stream("GET", url, timeout=10000.0) as response_stream:
        for partial_response in response_stream.iter_text(chunk_size=200):
            print(partial_response, end='')
            response += partial_response
    print()
    return response

PORT = 10000

external_repos = ["../continue", "../react"]
task = "Make a basic hello world vscode extension"

for repo_dir in external_repos:
    test_post_endpoint(f"http://localhost:{PORT}/init_external_repo_agent?repo_dir={repo_dir}")

test_get_endpoint(f"http://localhost:{PORT}/get_external_repo_agents")

subtasks = test_post_endpoint(f"http://localhost:{PORT}/generate_subtasks?objective={task}")
subtasks = json.loads(subtasks)

for subtask in subtasks:
    test_post_endpoint(f"http://localhost:{PORT}/run_subtask?subtask={subtask}")

test_get_endpoint(f"http://localhost:{PORT}/shutdown")
