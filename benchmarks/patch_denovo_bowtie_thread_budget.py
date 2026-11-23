"""Reproducible experimental override of *only* MiCall de novo Bowtie threads.

For comparison experiments, patch the shared MiCall base BEFORE deriving the
Ivanka image. Never patch just one arm, or alter the frozen baseline images.
"""
import ast
import importlib.util
import os
from pathlib import Path

def main():
    threads = int(os.environ.get("IVANKA_EXPERIMENT_BOWTIE_THREADS", "2"))
    if not 1 <= threads <= 16:
        raise ValueError("thread count must be in 1..16")
    spec = importlib.util.find_spec("micall.core.denovo_multimap")
    if spec is None or spec.origin is None:
        raise RuntimeError("pinned MiCall multimap module unavailable")
    path = Path(spec.origin)
    original = path.read_text()
    assignments = [stmt for stmt in ast.parse(original).body
                   if isinstance(stmt, ast.Assign)
                   and any(isinstance(t, ast.Name)
                           and t.id == "DENOVO_BOWTIE_THREADS"
                           for t in stmt.targets)]
    if (len(assignments) != 1 or
            not isinstance(assignments[0].value, ast.Constant) or
            assignments[0].value.value != 4):
        raise ValueError("unexpected MiCall baseline thread count")
    token = "DENOVO_BOWTIE_THREADS = 4"
    if original.count(token) != 1:
        raise ValueError("thread constant is not an exact single source token")
    updated = original.replace(token, f"DENOVO_BOWTIE_THREADS = {threads}")
    compile(updated, str(path), "exec")
    path.write_text(updated)
    print(f"MiCall Bowtie2 threads: {threads}, original: 4")

if __name__ == "__main__":
    main()
