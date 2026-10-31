from pathlib import Path
from .files import tracked, fanout
from .lines import effective_lines, crowded
from .python_deps import violations as python_imports
from .rust_deps import violations as rust_imports
from .shell_deps import violations as shell_imports

def source_kind(path, text):
    if path.suffix in (".py", ".rs", ".sh"):
        return path.suffix
    first = text.splitlines()[0] if text else ""
    if first.startswith("#!") and "python" in first:
        return ".py"
    if first.startswith("#!") and any(shell in first for shell in ("/sh", "bash", "zsh")):
        return ".sh"
    return None

def main():
    root = Path(__file__).resolve().parents[2]
    paths = tracked(root)
    problems = []
    for path in paths:
        text = (root / path).read_text(encoding="utf-8", errors="replace")
        kind = source_kind(path, text)
        if kind is None:
            continue
        source_path = path if path.suffix == kind else Path(str(path) + kind)
        count = effective_lines(source_path, text)
        if count > 50:
            problems.append(f"{path}: {count} effective lines (maximum 50)")
        for number in crowded(source_path, text):
            problems.append(f"{path}:{number}: multiple statements on one line")
        checker = {".py": python_imports, ".rs": rust_imports, ".sh": shell_imports}[kind]
        for problem in checker(root / path, text, root):
            problems.append(f"{path}: {problem}")
    for directory, count in fanout(paths):
        if count > 10:
            problems.append(f"{directory}: {count} direct entries (maximum 10)")
    for problem in sorted(problems):
        print(problem)
    if problems:
        print(f"{len(problems)} structural violations")
    else:
        print(f"Structural checks passed ({len(paths)} tracked/unignored files)")
    return bool(problems)

if __name__ == "__main__":
    raise SystemExit(main())
