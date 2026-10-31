import re
from pathlib import Path

def violations(path, text, root):
    problems = []
    for number, line in enumerate(text.splitlines(), 1):
        if re.match(r"^\s*eval\s+", line):
            problems.append(f"line {number}: dynamic shell execution")
        match = re.match(r"^\s*(?:source|\.)\s+(\S+)", line)
        if not match:
            continue
        name = match.group(1).strip("'\"")
        if "$" in name or "`" in name:
            problems.append(f"line {number}: dynamic shell source")
            continue
        target = Path(name)
        if target.is_absolute() or target.parent not in (Path("."),):
            problems.append(f"line {number}: non-sibling shell source {name}")
        elif not (path.parent / target.name).is_file():
            problems.append(f"line {number}: missing shell source {name}")
    return problems
