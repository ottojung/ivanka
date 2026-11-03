from pathlib import Path
import subprocess

def tracked(root):
    output = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
    )
    paths = [Path(name) for name in output.decode().split("\0") if name]
    return sorted(set(path for path in paths if (root / path).is_file()))

def fanout(paths):
    directories = {}
    for path in paths:
        for index, name in enumerate(path.parts):
            parent = Path(*path.parts[:index]) if index else Path(".")
            directories.setdefault(parent, set()).add(name)
    return sorted((str(parent), len(entries)) for parent, entries in directories.items())
