"""Experimental common MiCall Bowtie2 placement cap.

Derive BOTH IVA and Ivanka from a shared pinned MiCall image. The existing
non-stealing per-original-fragment accounting remains unchanged; only the
number of reported placements per original fragment is reduced.
"""
import ast
import importlib.util
import os
from pathlib import Path


def adjust(text: str, count: int) -> str:
    if not 1 <= count <= 12:
        raise ValueError("experimental Bowtie2 -k outside 1..12")
    matches = [node for node in ast.parse(text).body
               if isinstance(node, ast.Assign)
               and any(isinstance(x, ast.Name)
                       and x.id == "MAX_DENOVO_ALIGNMENTS"
                       for x in node.targets)]
    if (len(matches) != 1 or
            not isinstance(matches[0].value, ast.Constant) or
            matches[0].value.value != 12):
        raise ValueError("unexpected pinned MiCall mapping limit")
    needle = "MAX_DENOVO_ALIGNMENTS = 12"
    if text.count(needle) != 1:
        raise ValueError("MiCall source drift or duplicate limit")
    changed = text.replace(needle, f"MAX_DENOVO_ALIGNMENTS = {count}")
    compile(changed, "<micall-k-experiment>", "exec")
    return changed


def main():
    count = int(os.environ["IVANKA_EXPERIMENT_BOWTIE_K"])
    spec = importlib.util.find_spec("micall.core.denovo_multimap")
    if spec is None or not spec.origin:
        raise ValueError("Pinned MiCall multimap module missing")
    path = Path(spec.origin)
    path.write_text(adjust(path.read_text(), count))
    print("Experiment: Bowtie2 -k", count, "for BOTH arms")


if __name__ == "__main__":
    main()
