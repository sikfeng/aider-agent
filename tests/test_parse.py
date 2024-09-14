from raider_backend import parse

filename = '/workspace/sheetjs/xlsx.js'
filename = '/workspace/cody/vscode/src/completions/logger.ts'
res = parse.get_class_method_function_defs(filename)
print(res)
