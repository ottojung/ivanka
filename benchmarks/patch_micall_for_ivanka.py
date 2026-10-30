#!/usr/bin/env python3
"""Patch only MiCall's IVA assembler boundary for a containerized Ivanka comparison.

Usage (during Docker build): python patch_micall_for_ivanka.py
"""
import ast
import importlib.util
from pathlib import Path

spec = importlib.util.find_spec("micall.core.denovo")
assert spec is not None and spec.origin is not None
path = Path(spec.origin)
original = path.read_text()
lines = original.splitlines(keepends=True)
tree = ast.parse(original)
found = [item for item in tree.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "run_subprocess"]
assert len(found) == 1, "MiCall assembler interface changed: abort patch"
method = found[0]
assert {"fastq1", "fastq2", "merged_contigs_csv"} == {a.arg for a in method.args.args}, "MiCall assembler arguments changed"
begin = min([method.lineno] + [decorator.lineno for decorator in method.decorator_list])
end = method.end_lineno
assert "iva" in "".join(lines[begin-1:end]).lower(), "Not an IVA assembly boundary"
replacement = '''
@cached("denovo[ivanka]")
def run_subprocess(fastq1: Path, fastq2: Path, merged_contigs_csv: Optional[Path]) -> Path:
    # The MiCall sequencing, G2P, stitching and mapping stages remain untouched.
    # Ivanka currently has no --seeds interface; MiCall still appends the same
    # G2P-derived contigs to both assembler arms before stitching.
    work_dir = WorkDir.get()
    for existing in work_dir.glob("assembly_*"):
        shutil.rmtree(existing, ignore_errors=True)
    tmp_dir = Path(mkdtemp(dir=work_dir, prefix="assembly_"))
    output = tmp_dir / "ivanka_contigs.fasta"
    command = ["ivanka", "--reads1", str(fastq1),
               "--reads2", str(fastq2), "--output", str(output)]
    if merged_contigs_csv is not None:
        from csv import DictReader
        seed_fasta = tmp_dir / "g2p-seeds.fasta"
        with open(merged_contigs_csv) as source, seed_fasta.open("w") as target:
            for index, row in enumerate(DictReader(source)):
                sequence = row.get("contig", "").strip().upper()
                if sequence:
                    target.write(f">g2p_{index}\\n{sequence}\\n")
        if seed_fasta.stat().st_size:
            command.extend(["--seeds", str(seed_fasta)])
    logger.info("Running Ivanka assembler with MiCall G2P seed input.")
    subprocess.run(command, check=True, cwd=tmp_dir)
    if not output.is_file():
        raise RuntimeError("Ivanka returned success but wrote no FASTA")
    return output
'''
# Preserve MiCall's complete pre- and post-assembly pipeline unchanged.
new_source = "".join(lines[:begin-1]) + replacement + "".join(lines[end:])
compile(new_source, str(path), "exec")
path.write_text(new_source)
print("Replaced exactly the assembler run_subprocess in", path)
