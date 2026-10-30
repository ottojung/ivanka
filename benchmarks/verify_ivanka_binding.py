"""Fail closed unless the MiCall assembler boundary actually invokes Ivanka."""
from importlib.util import find_spec
from pathlib import Path

module = find_spec("micall.core.denovo")
if module is None or module.origin is None:
    raise SystemExit("MiCall denovo module missing")
source = Path(module.origin).read_text()
if 'command = ["ivanka", "--reads1"' not in source:
    raise SystemExit("MiCall assembler boundary does not invoke Ivanka")
if '@cached("denovo[ivanka]")' not in source:
    raise SystemExit("MiCall assembler cache key does not identify Ivanka")
if not Path("/usr/local/bin/ivanka").is_file():
    raise SystemExit("Ivanka executable missing from image")
