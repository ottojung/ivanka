"""Adjust only container resources, not inputs, MiCall, or scoring."""
import shutil

from benchmarks.expanded import micall_synthetic as original
from .synthetic_verify import verify


COMMAND = original.command


def command(*args):
    argv = COMMAND(*args)
    if argv.count("--memory=4g") != 1:
        raise ValueError("unexpected original container memory policy")
    argv[argv.index("--memory=4g")] = "--memory=5g"
    return argv


def install():
    original.command = command


def perform(tool, row, root, images):
    sample, source, manifest = row
    folder = root / sample / tool
    folder.parent.mkdir(exist_ok=True)
    record = original.attempt((source, manifest), folder, tool,
                              images[tool], 3000)
    checked = verify(folder, tool, images[tool])
    if checked != record:
        raise ValueError("new synthetic resource arm not authenticated")
    if record["status"] == "success":
        scratch = folder / "scratch"
        source_file = record["final_dominant"]["source_output"]
        if (not source_file.startswith("scratch/") and scratch.is_dir()
                and not scratch.is_symlink()):
            shutil.rmtree(scratch)
    return checked
