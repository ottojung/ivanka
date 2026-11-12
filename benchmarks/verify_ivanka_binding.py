"""Audit the exact MiCall subprocess and the pinned assembler implementation."""
import ast
import hashlib
import stat
import sys
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


EXTERNAL = ("haploflow", "megahit", "abyss", "spades", "velvet")


def verify_competitor_source(tool, configured, entrypoint, helpers,
                             expected_entrypoint_sha, expected_helpers_sha):
    """A competitor adapter is permitted ONLY for an explicitly selected arm."""
    if tool not in EXTERNAL or configured != tool:
        raise ValueError("wrong external assembler integration binding")
    for source, expected in ((entrypoint, expected_entrypoint_sha),
                             (helpers, expected_helpers_sha)):
        if (len(expected) != 64 or
                hashlib.sha256(source).hexdigest() != expected):
            raise ValueError("competitor image source digest mismatch")
    if not entrypoint.startswith(b"#!/opt/venv/bin/python"):
        raise ValueError("competitor entry point is not the reviewed adapter")
    tree = ast.parse(entrypoint)
    flags = [node.args[0].value for node in ast.walk(tree)
             if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute)
             and node.func.attr == "add_argument"
             and node.args and isinstance(node.args[0], ast.Constant)]
    if set(flags) != {"--reads1", "--reads2", "--output"}:
        raise ValueError("competitor adapter accepts unexpected parameters")


def verify_competitor_files(tool, expected_entrypoint_sha, expected_helpers_sha):
    root = Path("/usr/local/bin")
    entrypoint = root / "ivanka"
    helpers = root / "adapters.py"
    if not (entrypoint.is_file() and
            (entrypoint.stat().st_mode & stat.S_IXUSR)):
        raise ValueError("missing executable external adapter")
    configured = Path("/etc/ivanka-expanded-tool").read_text().strip()
    verify_competitor_source(
        tool, configured, entrypoint.read_bytes(), helpers.read_bytes(),
        expected_entrypoint_sha, expected_helpers_sha)


def main():
    module = find_spec("micall.core.denovo")
    if module is None or module.origin is None:
        raise SystemExit("MiCall denovo module missing")
    verify_source(Path(module.origin).read_text())
    args = sys.argv[1:]
    if not args:
        path = Path("/usr/local/bin/ivanka")
        if not path.is_file() or path.open("rb").read(4) != b"\x7fELF":
            raise SystemExit("Ivanka entry point must be the native Rust ELF binary")
    elif len(args) == 4 and args[0] == "--competitor":
        verify_competitor_files(args[1], args[2], args[3])
    else:
        raise SystemExit("unexpected candidate verification mode")


if __name__ == "__main__":
    main()
