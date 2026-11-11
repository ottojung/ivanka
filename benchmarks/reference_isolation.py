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
# Explicitly reviewed source-to-image paths. Any newly added Python code
# copied into an Ivanka/MiCall candidate image requires a boundary review,
# regardless of its filename. The conserved remap experiment is downstream:
# it uses the produced MiCall remap reference, never as an assembler input.
IMAGE_SCRIPT_ROLES = {
    "patch_micall_for_ivanka.py": "candidate",
    "verify_ivanka_binding.py": "candidate",
    "ivanka_read_support_selector.py": "candidate",
    "ivanka_trim_unsupported.py": "candidate",
    "ivanka_read_window.py": "candidate",
    "ivanka_read_tiling.py": "candidate",
    "patch_micall_stitcher_kmer_veto.py": "candidate",
    "patch_remap_threads.py": "candidate",
    "patch_micall_conserved_remap.py": "candidate",
    "conserved_pair_remap.py": "downstream",
}
COPY_SCRIPT = re.compile(
    r"(?im)^\s*(?:COPY|ADD)\s+benchmarks/([^\s]+\.py)\s+[^\n]+"
)
COPY_BROAD = re.compile(
    r"(?im)^\s*(?:COPY|ADD)\s+(?:\.|benchmarks/?)\s+"
)


def image_script_errors(name, contents, root=ROOT):
    """Fail closed on unreviewed executable sources in candidate images."""
    errors = []
    if COPY_BROAD.search(contents):
        errors.append(f"{name}: broad COPY would bypass assembler-source review")
    for script in COPY_SCRIPT.findall(contents):
        role = IMAGE_SCRIPT_ROLES.get(script)
        if role is None:
            errors.append(f"{name}: unreviewed image Python script: {script}")
            continue
        path = root / "benchmarks" / script
        if not path.is_file():
            errors.append(f"{name}: missing copied Python script: {script}")
        elif role == "candidate":
            errors.extend(candidate_source_errors(str(path.relative_to(root)), path.read_text()))
    return errors


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
    # Candidate selectors are checked even when not currently installed by
    # an image. Build-time copying is independently reviewed by a fixed list.
    candidate_paths = set((root / "benchmarks").glob("ivanka_*.py"))
    candidate_paths.update((root / "benchmarks").glob("*selector*.py"))
    candidate_paths.update((root / "benchmarks").glob("*postselect*.py"))
    candidate_paths.update(root / "benchmarks" / name for name, role in
                           IMAGE_SCRIPT_ROLES.items() if role == "candidate")
    for path in sorted(candidate_paths):
        if path.is_file() and not path.name.startswith("test_"):
            errors += candidate_source_errors(str(path.relative_to(root)), path.read_text())
    recipes = [p for p in (root / "benchmarks").rglob("*")
               if p.is_file() and p.name.startswith(("Dockerfile", "Containerfile"))]
    for path in sorted(recipes):
        text = path.read_text()
        name = str(path.relative_to(root))
        errors += image_recipe_errors(name, text)
        errors += image_script_errors(name, text, root)
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
