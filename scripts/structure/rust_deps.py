from .rust_lines import without_comments
import re

def sibling(directory, name):
    return (directory / (name + ".rs")).is_file() or (directory / name).is_dir()

def violations(path, text, root):
    problems = []
    text = without_comments(text)
    if "#[path" in text:
        problems.append("explicit Rust module path override")
    if "include!(" in text:
        problems.append("generated Rust source include")
    for match in re.finditer("^[ \t]*mod +([A-Za-z_][A-Za-z0-9_]*) *;", text, re.MULTILINE):
        if not sibling(path.parent, match.group(1)):
            problems.append(f"missing sibling module {match.group(1)}")
    for match in re.finditer("^[ \t]*use +([^;]+);", text, re.MULTILINE):
        statement = match.group(1).strip()
        prefix = next((p for p in ("crate::", "super::", "self::")
                       if statement.startswith(p)), None)
        if prefix is None:
            first = re.match("[A-Za-z_][A-Za-z0-9_]*", statement)
            if first is None or not sibling(path.parent, first.group()):
                continue
            remainder = statement
        else:
            remainder = statement[len(prefix):]
        if remainder.startswith(("super::", "self::", "crate::")):
            problems.append(f"non-sibling Rust import {statement}")
            continue
        base = root / "src" if prefix == "crate::" else path.parent
        first = re.match("[A-Za-z_][A-Za-z0-9_]*", remainder)
        if base != path.parent or first is None or not sibling(base, first.group()):
            problems.append(f"non-sibling Rust import {statement}")
            continue
        tail = remainder[first.end():]
        if tail.startswith("::"):
            item = re.match("::([A-Za-z_][A-Za-z0-9_]*)", tail)
            if item and sibling(base / first.group(), item.group(1)):
                problems.append(f"descendant Rust import {statement}")
            if tail.count("::") > 1:
                problems.append(f"deep Rust import {statement}")
    return problems
