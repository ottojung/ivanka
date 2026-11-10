"""CI-enforced boundary: candidate assembly must not see benchmark references.

References belong solely to external MiCall stages and independent scoring.
This lexical and interface guard is defense in depth, not a substitute for
reviewing which sources a newly introduced execution adapter can access.
"""
import ast
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN_ASSEMBLER = re.compile(
    r"(?i)(?:\bhxb2\b|\breference[_-]?panel\b|"
    r"\breference[_-]?(?:genome|fasta|catalog)\b|"
    r"\bbenchmark[_-]?panel\b|"
    r"\bivanka[_-](?:reference|diagonal)[_-]selector\b|"
    r"--(?:reference|ref|panel)(?:\b|=))"
)
FORBIDDEN_CANDIDATE = re.compile(
    r"(?i)(?:\b(?:reference|references|reference21|ref21|hxb2|"
    r"panel|diagonal|alignment[_-]?score|iva[_-]?score)\b|"
    r"\bivanka[_-](?:reference|diagonal)[_-]selector\b|"
    r"\breference[_-]?(?:panel|catalog|genome|fasta)\b|"
    r"\bbuild_position_index\b|\bindex_references\b)"
)
FORBIDDEN_IMAGE_COPY = re.compile(
    r"(?im)^\s*(?:COPY|ADD)\s+[^\n]*(?:"
    r"reference[_-]?panel|reference[_-]?catalog|"
    r"hxb2|ivanka[_-](?:reference|diagonal)[_-]selector|"
    r"reference[_-].*\.(?:fa|fasta|json|gz))"
)


def assembler_source_errors(name, contents):
    found = FORBIDDEN_ASSEMBLER.search(contents)
    return [f"{name}: assembler may not use known references ({found.group()})"] if found else []


def candidate_source_errors(name, contents):
    found = FORBIDDEN_CANDIDATE.search(contents)
    return [f"{name}: candidate selector/adapter may not score against references ({found.group()})"] if found else []


def image_recipe_errors(name, contents):
    found = FORBIDDEN_IMAGE_COPY.search(contents)
    return [f"{name}: assembler image may not import reference material ({found.group().strip()})"] if found else []


def adapter_contract_errors(source):
    """Check the exact executable command in the sole MiCall assembler adapter."""
    tree = ast.parse(source)
    assignments = [n for n in tree.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "replacement"
                           for t in n.targets)]
    if len(assignments) != 1:
        return ["MiCall adapter must expose exactly one pinned replacement"]
    try:
        body = ast.literal_eval(assignments[0].value)
        inner = ast.parse(body)
    except (ValueError, SyntaxError, TypeError) as exc:
        return [f"Cannot inspect MiCall assembler adapter: {exc}"]
    functions = [node for node in inner.body
                 if isinstance(node, ast.FunctionDef)
                 and node.name == "run_subprocess"]
    if len(functions) != 1:
        return ["Missing sole MiCall run_subprocess boundary"]
    function = functions[0]
    if sorted(a.arg for a in function.args.args) != sorted(
        ("fastq1", "fastq2", "merged_contigs_csv")
    ):
        return ["MiCall run_subprocess signature changed; review boundary"]
    # The current default adapter consumes two FASTQs, without forwarding
    # optional seeds. The standalone Ivanka CLI accepts trusted read-derived
    # FASTA seeds; wiring seeds into the adapter needs provenance review.
    if re.search(r'--(?:reference|ref|panel|genome)\b', body):
        return ["MiCall adapter forwards a reference-related parameter"]
    for node in ast.walk(function):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id == "merged_contigs_csv":
                return ["Default MiCall adapter now reads auxiliary seed data; document provenance and review"]
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in ("open", "read_text", "read_bytes"):
                return ["MiCall adapter reads an auxiliary file"]
    calls = [node for node in ast.walk(function)
             if isinstance(node, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == "command"
                     for t in node.targets)]
    if len(calls) != 1 or not isinstance(calls[0].value, ast.List):
        return ["Assembler command no longer has a statically inspectable interface"]
    tokens = [elt.value for elt in calls[0].value.elts
              if isinstance(elt, ast.Constant) and isinstance(elt.value, str)]
    if tokens != ["ivanka", "--reads1", "--reads2", "--output"]:
        return [f"Assembler receives unexpected input parameters: {tokens}"]
    return []


def check_repository(root=ROOT):
    errors = []
    for path in sorted((root / "src").rglob("*.rs")):
        text = path.read_text()
        errors += assembler_source_errors(str(path.relative_to(root)), text)
    for path in sorted((root / "benchmarks").glob("ivanka_*.py")):
        errors += candidate_source_errors(str(path.relative_to(root)), path.read_text())
    for path in sorted((root / "benchmarks").glob("*postselect*.py")):
        errors += candidate_source_errors(str(path.relative_to(root)), path.read_text())
    for path in sorted((root / "benchmarks").glob("Dockerfile*")):
        errors += image_recipe_errors(str(path.relative_to(root)), path.read_text())
    adapter = root / "benchmarks" / "patch_micall_for_ivanka.py"
    text = adapter.read_text()
    errors += candidate_source_errors(str(adapter.relative_to(root)), text)
    errors += adapter_contract_errors(text)
    return errors


if __name__ == "__main__":
    errors = check_repository()
    if errors:
        raise SystemExit("Reference isolation FAILED:\n" + "\n".join(errors))
    print("Reference isolation PASS: no known-reference selection; read-derived seeds allowed")
