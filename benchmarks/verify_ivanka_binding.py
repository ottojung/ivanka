"""Fail closed unless MiCall's real assembler subprocess invokes Ivanka."""
import ast
from importlib.util import find_spec
from pathlib import Path


def verify_source(source):
    tree = ast.parse(source)
    methods = [node for node in tree.body
               if isinstance(node, ast.FunctionDef)
               and node.name == "run_subprocess"]
    if len(methods) != 1:
        raise ValueError("Exactly one MiCall run_subprocess required")
    method = methods[0]
    decorators = [node for node in method.decorator_list
                  if isinstance(node, ast.Call)
                  and isinstance(node.func, ast.Name)
                  and node.func.id == "cached"
                  and len(node.args) == 1
                  and isinstance(node.args[0], ast.Constant)
                  and node.args[0].value == "denovo[ivanka]"]
    if len(decorators) != 1:
        raise ValueError("MiCall assembler cache key must identify Ivanka")
    assignments = [node.value for node in ast.walk(method)
                   if isinstance(node, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "command"
                           for t in node.targets)]
    if len(assignments) != 1 or not isinstance(assignments[0], ast.List):
        raise ValueError("MiCall assembler command assignment changed")
    literals = [node.value for node in assignments[0].elts
                if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    if literals != ["ivanka", "--reads1", "--reads2", "--output"]:
        raise ValueError("MiCall subprocess does not invoke Ivanka with both mates")


def main():
    module = find_spec("micall.core.denovo")
    if module is None or module.origin is None:
        raise SystemExit("MiCall denovo module missing")
    verify_source(Path(module.origin).read_text())
    if not Path("/usr/local/bin/ivanka").is_file():
        raise SystemExit("Ivanka executable missing from image")


if __name__ == "__main__":
    main()
