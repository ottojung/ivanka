#!/usr/bin/env python3
"""Experimentally parallelize the pinned MiCall Bowtie2 contig remapper.

Fails closed if the exact map_to_reference source contract has changed.
This never patches the IVA control image.
"""
import argparse
import ast
from importlib.util import find_spec
from pathlib import Path


def patch_remap_source(source: str, threads: int) -> str:
    if not 2 <= threads <= 32:
        raise ValueError("Experimental remap thread count must be 2..32")
    tree = ast.parse(source)
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name == "map_to_reference"]
    if len(functions) != 1:
        raise ValueError("Expected exactly one MiCall map_to_reference")
    assignments = [node for node in ast.walk(functions[0])
                   if isinstance(node, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "bowtie_args"
                           for t in node.targets)]
    if len(assignments) != 1 or not isinstance(assignments[0].value, ast.List):
        raise ValueError("Expected exactly one Bowtie2 arguments list")
    elements = assignments[0].value.elts
    flags = [i for i, node in enumerate(elements)
             if isinstance(node, ast.Constant) and node.value == "-p"]
    if len(flags) != 1 or flags[0] + 1 >= len(elements):
        raise ValueError("Expected exactly one Bowtie2 -p argument")
    node = elements[flags[0] + 1]
    if not isinstance(node, ast.Constant) or node.value != "1":
        raise ValueError("Only the original single-thread MiCall remapper is supported")
    if any(isinstance(n, ast.Constant) and n.value == "--reorder" for n in elements):
        raise ValueError("MiCall already specifies reordered output")
    lines = source.splitlines(keepends=True)
    start = sum(len(s) for s in lines[:node.lineno - 1]) + node.col_offset
    end = sum(len(s) for s in lines[:node.end_lineno - 1]) + node.end_col_offset
    literal = source[start:end]
    if literal not in ("'1'", '"1"'):
        raise ValueError("Unsupported Bowtie2 thread-count source syntax")
    patched = source[:start] + literal[0] + str(threads) + literal[0] + ", '--reorder'" + source[end:]
    compile(patched, "<patched MiCall remap>", "exec")
    return patched


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--threads", type=int, required=True)
    args = parser.parse_args()
    spec = find_spec("micall.core.remap")
    if spec is None or spec.origin is None:
        raise RuntimeError("MiCall remap module not installed")
    file = Path(spec.origin)
    source = file.read_text()
    patched = patch_remap_source(source, args.threads)
    file.write_text(patched)
    print(f"MiCall experimental Bowtie2 threads={args.threads} with ordered SAM output")


if __name__ == "__main__":
    main()
