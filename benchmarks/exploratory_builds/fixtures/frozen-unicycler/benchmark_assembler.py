"""One fixed assembler per branch: no selector or reference dependency."""
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp
import subprocess
from micall.utils.work_dir import WorkDir


def assemble(first: Path, second: Path, seeds: Path | None) -> Path:
    """Run unicycler short-read mode with fixed CLI options and the paired reads."""
    parent = WorkDir.get()
    for leftover in parent.glob("assembly_*"):
        rmtree(leftover, ignore_errors=True)
    work = Path(mkdtemp(dir=parent, prefix="assembly_"))
    output = work / "unicycler" / "assembly.fasta"
    # Illumina-only de novo path: -1/-2 are the original paired FASTQ files.
    # No reference, truth, target or score-selected contig is ever passed.
    # Short-read Unicycler is a SPAdes optimiser (spades.py is called by the
    # pinned SPAdes build in the image); disclosed as non-independent.
    steps = [[
        "unicycler", "-1", str(first), "-2", str(second),
        "-o", str(work / "unicycler"), "-t", "2",
    ]]
    with (work / "assembler.log").open("wb") as log:
        for argv in steps:
            subprocess.run(argv, check=True, cwd=work,
                           env=None,
                           stdout=log, stderr=subprocess.STDOUT)
    if not output.is_file():
        raise RuntimeError("unicycler completed without the expected FASTA")
    return output
