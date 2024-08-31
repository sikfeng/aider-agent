from search_manage import SearchManager

#search_manager = SearchManager("/workspace/cody/")
#class_name = "BfgRetriever"

#search_manager = SearchManager("/workspace/sample_js_repo/")
#class_name = "ErrorBoundary"
#result, _, _ = search_manager.search_class(class_name)
#result, _, _ = search_manager.get_class_full_snippet(class_name)
#result = search_manager.search_method_in_file("PureComponent", "ReactBaseClasses.js")
#result = search_manager.search_method_in_file("get_class_signature", "search_utils.py")
#result = search_manager.search_method_in_class("getDerivedStateFromError", "ErrorBoundary")

#print(result)

search_manager = SearchManager("/workspace/sample_js_repo/")
#class_name = "SearchManager"
class_name = "ErrorBoundary"
result, _, _ = search_manager.search_class(class_name)

print(result)

import search_utils

result = ""

#result = search_utils.parse_python_file('/workspace/react/fixtures/fiber-debugger/src/App.js')
#result = search_utils.parse_file('/workspace/react/fixtures/fiber-debugger/src/App.js')

#result = search_utils.parse_python_file('/workspace/auto-code-rover/app/search/search_utils.py')
#result = search_utils.parse_file('/workspace/auto-code-rover/app/search/search_utils.py')

#result = search_utils.parse_python_file('/workspace/sample_js_repo/ReactBaseClasses.js')
#result = search_utils.parse_file('/workspace/sample_js_repo/ReactBaseClasses.js')

#result = search_utils.parse_python_file('/workspace/sample_js_repo/ErrorBoundary.js')
#result = search_utils.parse_file('/workspace/sample_js_repo/ErrorBoundary.js')

#print(result)

