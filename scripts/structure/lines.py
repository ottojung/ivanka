import io
import tokenize

def python_lines(text):
    lines = text.splitlines()
    comments = set()
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        for token in tokens:
            if token.type == tokenize.COMMENT:
                index, column = token.start
                if not lines[index - 1][:column].strip():
                    comments.add(index - 1)
    except (tokenize.TokenError, IndentationError):
        pass
    return sum(bool(line.strip()) and i not in comments for i, line in enumerate(lines))

from .rust_lines import rust_lines, without_comments

def effective_lines(path, text):
    if path.suffix == ".py":
        return python_lines(text)
    if path.suffix == ".rs":
        return rust_lines(text)
    return sum(bool(line.strip()) and not line.lstrip().startswith("#")
               for line in text.splitlines())

def crowded(path, text):
    if path.suffix == ".py":
        import ast
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return []
        counts = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.stmt) and hasattr(node, "lineno"):
                counts[node.lineno] = counts.get(node.lineno, 0) + 1
        return sorted(number for number, count in counts.items() if count > 1)
    if path.suffix == ".rs":
        return [number for number, line in enumerate(without_comments(text).splitlines(), 1)
                if line.count(";") > 1]
    return []
