"""Stage six reproducible fresh, both-arm MiCall comparison runs.

The existing IVA control and MiCall base are pinned. Each candidate image
must expose the *same* reads1/reads2/output adapter and label its assembler.
No cached controls, imported samples or reference-fed assembler seeds.
"""
import argparse
import json
import os
from pathlib import Path
import random
import subprocess
import sys

from .adapters import ASSEMBLERS

IVA_BASE = "a5d4923e28f3d7b9725a375d51e34b14986bd29bdab04e8bf8f36f411141b8dd"
MAX_SECONDS = 1800


def inspect(image, template):
    return subprocess.check_output(
        ["podman", "image", "inspect", "--format", template, image],
        text=True, timeout=60).strip()


def verify_images(images):
    """Require exact immutable image IDs and one original updated MiCall base."""
    if set(images) != set(ASSEMBLERS):
        raise ValueError("six candidate images plus pinned IVA control required")
    if images["iva"] != IVA_BASE:
        raise ValueError("unexpected IVA control image: qualification changed")
    base = json.loads(inspect(IVA_BASE, "{{json .RootFS.Layers}}"))
    for name, image in images.items():
        if (len(image) != 64 or any(c not in "0123456789abcdef" for c in image)
                or inspect(image, "{{.Id}}").removeprefix("sha256:") != image):
            raise ValueError(f"{name}: image must be an immutable full digest")
        layers = json.loads(inspect(image, "{{json .RootFS.Layers}}"))
        if layers[:len(base)] != base:
            raise ValueError(f"{name}: MiCall base layers do not match IVA")
        if name == "iva":
            continue
        labels = json.loads(inspect(image, "{{json .Config.Labels}}"))
        label = labels.get("org.ottojung.expanded.assembler")
        # The first-party Ivanka image predates this new suite's label.
        if label != name and not (name == "ivanka"
              and labels.get("org.ottojung.ivanka.execution")
                  == "native-fastq-read-backed-selector-trim-island-tile512"):
            raise ValueError(f"{name}: image lacks verified tool-binding label")


def run(dataset, results, images, *, jobs=10, runner=None):
    if not 1 <= jobs <= 10:
        raise ValueError("sample workers must be in 1..10")
    verify_images(images)
    result_root = Path(results)
    result_root.mkdir(parents=True, exist_ok=False)
    runner = Path(runner or Path(__file__).resolve().parents[1] / "podman_full_micall.py")
    order = [tool for tool in ASSEMBLERS if tool != "iva"]
    random.Random(20261112).shuffle(order)
    audit = {"schema": "ivanka.expanded.real_runs.v1",
             "images": images, "order": order, "status": {}}
    for name in order:
        folder = result_root / name
        folder.mkdir()
        env = os.environ.copy()
        env.update({
            "IVANKA_DATA": str(Path(dataset).resolve()),
            "IVANKA_PODMAN_RESULTS": str(folder.resolve()),
            "IVANKA_IVA_IMAGE": images["iva"],
            "IVANKA_IVANKA_IMAGE": images[name],
            "IVANKA_PODMAN_LIFECYCLE": "detached",
        })
        argv = [sys.executable, str(runner), "--mode", "both",
                "--jobs", str(jobs), "--parallel-arms", "--all-projects",
                "--timeout-per-arm", str(MAX_SECONDS),
                "--sample-time-limit", str(MAX_SECONDS),
                "--diagnostic-90-floor"]
        with (folder / "runner.log").open("x") as stream:
            completed = subprocess.run(
                argv, cwd=runner.parent.parent, env=env,
                stdout=stream, stderr=subprocess.STDOUT, check=False,
            )
        terminal = list(folder.glob("summary-*.json"))
        audit["status"][name] = {
            "exit_code": completed.returncode,
            "summary_count": len(terminal),
            "results_jsonl": str(folder / "results.jsonl"),
        }
        (result_root / "execution_manifest.json").write_text(
            json.dumps(audit, sort_keys=True, indent=2)+"\n")
        # Diagnostic 90%-floor failures of a competitor are NOT a reason
        # to skip recording it. The downstream real_matrix validator will
        # separate clean weak scores from genuine execution failures.
    return audit


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--images", required=True, type=Path,
                        help="JSON mapping all seven tool names to full immutable image IDs")
    parser.add_argument("--jobs", type=int, default=10)
    args = parser.parse_args(argv)
    result = run(args.data, args.out, json.loads(args.images.read_text()), jobs=args.jobs)
    print(json.dumps(result, sort_keys=True))
    print("NOT A PASS: run expanded.real_matrix, then combine with synthetic "
          "results and require expanded.gate to return zero.")


if __name__ == "__main__":
    main()
