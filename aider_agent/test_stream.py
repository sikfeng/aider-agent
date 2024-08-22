import requests
import json

def test_post_endpoint(url, data=None):
    response = ""

    for partial_response in requests.post(
        url,
        stream = True,
        json = data
    ).iter_content(chunk_size=200, decode_unicode=True):
        if isinstance(partial_response, bytes):
            partial_response = partial_response.decode('utf-8')
        print(partial_response, end='')
        response += partial_response
    print()
    return response

def test_get_endpoint(url):
    response = ""

    for partial_response in requests.get(
        url,
        stream = True
    ).iter_content(chunk_size=200, decode_unicode=True):
        if isinstance(partial_response, bytes):
            partial_response = partial_response.decode('utf-8')
        print(partial_response, end='')
        response += partial_response
    print()
    return response

test_post_endpoint("http://localhost:8080/generate_subtasks?objective=write%20a%20vscode%20extension%20with%20a%20webview")
#test_post_endpoint("http://localhost:8080/confirm_run_subtasks", data = [
#        "Set up a new Visual Studio Code extension project using the Yeoman generator for VS Code extensions.",
#        "Configure the project by updating the package.json file with extension details such as name, displayName, description, version, and publisher."
#    ])
test_post_endpoint("http://localhost:8080/run_subtask?subtask=Create%20a%20new%20command%20in%20the%20package.json%20file%20that%20will%20trigger%20the%20webview.")
test_get_endpoint("http://localhost:8080/undo_last_subtask")
