"""Experiment: constrain only Ivanka's emitted contig budget in pinned MiCall.

Apply to the assembler-substitution image *after* installing the verified
Ivanka binary. No changes to the IVA arm or MiCall remapping logic.
"""
import ast
import importlib.util
import os
from pathlib import Path


def patch_source(source: str) -> str:
    tree = ast.parse(source)
    functions = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef)
                 and node.name == "run_subprocess"]
    if len(functions) != 1:
        raise ValueError("Missing unique MiCall assembly boundary")
    method = functions[0]
    if not any(isinstance(d, ast.Call)
               and isinstance(d.func, ast.Name) and d.func.id == "cached"
               and d.args and isinstance(d.args[0], ast.Constant)
               and d.args[0].value == "denovo[ivanka]"
               for d in method.decorator_list):
        raise ValueError("Ivanka assembler cache key not present")
    assignments = [
        stmt for stmt in ast.walk(method)
        if isinstance(stmt, ast.Assign)
        and any(isinstance(x, ast.Name) and x.id == "command"
                for x in stmt.targets)
    ]
    if len(assignments) != 1 or not isinstance(assignments[0].value, ast.List):
        raise ValueError("Unexpected assembler invocation structure")
    literals = [x.value for x in assignments[0].value.elts
                if isinstance(x, ast.Constant) and isinstance(x.value, str)]
    if literals != ["ivanka", "--reads1", "--reads2", "--output"]:
        raise ValueError("Unexpected pinned binary invocation")
    if "IVANKA_MAX_CONTIGS" in source:
        raise ValueError("Already patched or unrecognized code")
    line = assignments[0].end_lineno
    lines = source.splitlines(keepends=True)
    updated = "".join(
        lines[:line] + [
            '    import os\n',
            '    limit = int(os.environ["IVANKA_MAX_CONTIGS"])\n',
            '    if not 1 <= limit <= 1000:\n',
            '        raise ValueError("Invalid Ivanka contig budget")\n',
            '    command.extend(["--max-contigs", str(limit)])\n',
        ] + lines[line:]
    )
    compile(updated, "<pinned-ivanka-contig-budget>", "exec")
    return updated


def main():
    count = int(os.environ["IVANKA_MAX_CONTIGS"])
    if not 1 <= count <= 1000:
        raise ValueError("Contig budget out of range")
    spec = importlib.util.find_spec("micall.core.denovo")
    if spec is None or not spec.origin:
        raise ValueError("Missing MiCall module")
    path = Path(spec.origin)
    path.write_text(patch_source(path.read_text()))
    print("Experimentally limited Ivanka to", count, "candidate contigs")


if __name__ == "__main__":
    main()
