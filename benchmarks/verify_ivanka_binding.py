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
    if literals != ["/usr/local/bin/ivanka", "--reads1", "--reads2", "--output"]:
        raise ValueError("MiCall subprocess does not invoke Ivanka with both mates")
    args = assignments[0].elts
    if len(args) != 7:
        raise ValueError("MiCall assembler must have exactly three CLI arguments")
    for position in (2, 4, 6):
        expression = args[position]
        if (not isinstance(expression, ast.Call)
                or not isinstance(expression.func, ast.Name)
                or expression.func.id != "str"
                or len(expression.args) != 1
                or not isinstance(expression.args[0], ast.Name)):
            raise ValueError("MiCall assembler argument is not a direct input path")
    sources = [args[position].args[0].id for position in (2, 4, 6)]
    if sources not in (["fastq1", "fastq2", "output"],):
        raise ValueError("MiCall assembler input/output positions changed")
    invocations = [node for node in ast.walk(method)
                   if isinstance(node, ast.Call)
                   and isinstance(node.func, ast.Attribute)
                   and isinstance(node.func.value, ast.Name)
                   and node.func.value.id == "subprocess"
                   and node.func.attr == "run"]
    if len(invocations) != 1:
        raise ValueError("MiCall must invoke exactly one Ivanka subprocess")
    environment = [kw.value for kw in invocations[0].keywords if kw.arg == "env"]
    if len(environment) != 1 or not isinstance(environment[0], ast.Dict) or environment[0].keys:
        raise ValueError("Ivanka child environment must be empty")
    mutations = [node for node in ast.walk(method)
                 if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute)
                 and isinstance(node.func.value, ast.Name)
                 and node.func.value.id == "command"
                 and node.func.attr in ("append", "extend", "insert", "pop", "remove")]
    if mutations:
        raise ValueError("MiCall assembler command may not be mutated")


def main():
    module = find_spec("micall.core.denovo")
    if module is None or module.origin is None:
        raise SystemExit("MiCall denovo module missing")
    verify_source(Path(module.origin).read_text())
    path = Path("/usr/local/bin/ivanka")
    if not path.is_file() or path.open("rb").read(4) != b"\x7fELF":
        raise SystemExit("Ivanka entry point must be the native Rust ELF binary")


if __name__ == "__main__":
    main()
