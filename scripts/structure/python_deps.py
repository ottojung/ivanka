import ast

def location(name, directory, root):
    first = name.split(".")[0]
    for base in (directory, root):
        if (base / (first + ".py")).is_file() or (base / first).is_dir():
            return base
    return None

def violations(path, text, root):
    problems = []
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        return [f"invalid Python syntax: {exc}"]
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in ("exec", "eval", "compile", "__import__"):
                problems.append(f"line {node.lineno}: dynamic Python execution")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "importlib" and node.func.attr == "import_module":
                problems.append(f"line {node.lineno}: dynamic Python import")
        if isinstance(node, ast.Import):
            entries = [(alias.name, 0, ()) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            entries = [(node.module or "", node.level, node.names)]
        else:
            continue
        for name, level, names in entries:
            if level > 1:
                problems.append(f"line {node.lineno}: parent-relative import")
                continue
            if level == 1:
                if not name:
                    continue
                base = path.parent
            else:
                base = location(name, path.parent, root)
                if base is None:
                    continue
            if base != path.parent or "." in name:
                problems.append(f"line {node.lineno}: non-sibling import {name}")
                continue
            target = path.parent / name
            if target.is_dir():
                for alias in names:
                    if (target / (alias.name + ".py")).exists() or (target / alias.name).is_dir():
                        problems.append(f"line {node.lineno}: descendant import {name}.{alias.name}")
    return problems
