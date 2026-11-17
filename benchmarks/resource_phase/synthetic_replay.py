"""Recovery of original and resource-adjusted synthetic checkpoints."""

from benchmarks.expanded.comparators_first_synthetic import TOOLS
from benchmarks.expanded.micall_checkpoint import identity, write_case
from .synthetic_verify import verify


def prepare(folder, images):
    result = {}
    for tool in TOOLS:
        path = folder / tool
        record = verify(path, tool, images[tool])
        if record is not None:
            result[tool] = record
        elif path.exists():
            archive = folder / "_interrupted"
            archive.mkdir(exist_ok=True)
            for count in range(1, 1000):
                target = archive / f"{tool}-{count:03d}"
                if not target.exists():
                    path.rename(target)
                    break
            else:
                raise ValueError("too many interrupted synthetic arms")
    return result


def completed(folder, row, proof, results):
    sample, _, manifest = row
    return {**identity(sample, manifest, proof),
            "execution_order": list(TOOLS), "results": dict(results),
            "ivanka_deferred": True}


def write_completed(folder, row, proof, results):
    write_case(folder, completed(folder, row, proof, results))


