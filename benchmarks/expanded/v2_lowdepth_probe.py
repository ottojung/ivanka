"""Resumable source-attested 16-case v2 pilot across seven immutable MiCall images.

This is a separate NON-QUALIFYING experiment. It never changes the
original 400-case benchmark or promotes reused evidence to a win.
"""
import argparse
import json
from pathlib import Path

from .adapters import ASSEMBLERS
from .fork_micall_synthetic import checked_images
from .hxb2_cohort import attestation
from .micall_checkpoint import (
    digest, existing_case, identity, preserve_interrupted,
)
from .micall_lock import exclusive_lock
from .micall_retention import prune_case
from .micall_synthetic import run_case
from .run_synthetic import cohort_rows

SCHEMA = "ivanka.expanded.hxb2_lowdepth_v2_probe.v1"
SAMPLES = tuple(f"low_depth-s{i:03d}" for i in range(16))


def only_changed(cases):
    selected = {case[0]: case for case in cases if case[0] in SAMPLES}
    if set(selected) != set(SAMPLES):
        raise ValueError("all sixteen changed low-depth cases required")
    if any(case[2].get("pairs") != 5000 for case in selected.values()):
        raise ValueError("unexpected v2 low-depth input coverage")
    return [selected[name] for name in SAMPLES]


def pinned_manifest(proof, images, attestation_file, base):
    if proof.get("schema") != "ivanka.hxb2_truth_validation.v2":
        raise ValueError("only the verified v2 HXB2 input is permitted")
    if set(images) != set(ASSEMBLERS):
        raise ValueError("all seven original source-pinned MiCall images required")
    source = Path(__file__).resolve()
    scripts = (source, source.with_name("micall_synthetic.py"),
               source.with_name("micall_checkpoint.py"),
               source.with_name("micall_dominant.py"),
               source.with_name("score.py"),
               source.with_name("hxb2_cohort.py"),
               source.with_name("hxb2_lowdepth_v2.py"),
               source.parents[1] / "reference_panel.py",
               source.parents[1] / "inside_container_timing.py")
    return {"schema": SCHEMA, "qualification": "NOT_EVALUATED",
            "expected": 16, "truth_proof": proof,
            "images": images, "base_image": base,
            "fork_attestation_sha256": digest(attestation_file),
            "scripts_sha256": {part.name: digest(part) for part in scripts}}


def run(data, output, images, source_attestation, fork, base, *,
        timeout=1800, max_new=1):
    if timeout != 1800 or max_new not in range(0, 17):
        raise ValueError("the unchanged 1800s arm deadline is mandatory")
    output = Path(output)
    proof = attestation(data, expected=400)
    checked_images(images, source_attestation, fork, base)
    cases = only_changed(cohort_rows(data))
    frozen = pinned_manifest(proof, images, source_attestation, base)
    with exclusive_lock(output):
        if not output.exists():
            output.mkdir(parents=True)
        path = output / "run_manifest.json"
        if path.exists():
            if json.loads(path.read_text()) != frozen:
                raise ValueError("refuse to mix changed images, inputs, or code")
        else:
            path.write_text(json.dumps(frozen, sort_keys=True, indent=2) + "\n")
        result_file = output / "results.jsonl"
        logged = {}
        if result_file.is_file():
            for line in result_file.read_text().splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if row["id"] in logged:
                    raise ValueError("duplicate v2 pilot result")
                logged[row["id"]] = row
        count = 0
        with result_file.open("a", buffering=1) as stream:
            for case in cases:
                identifier, _, manifest = case
                cached = existing_case(
                    output / identifier,
                    identity(identifier, manifest, proof), images)
                if cached is not None:
                    if identifier in logged and logged[identifier] != cached:
                        raise ValueError("changed committed pilot result")
                    if identifier not in logged:
                        stream.write(json.dumps(cached, sort_keys=True) + "\n")
                    continue
                if identifier in logged:
                    raise ValueError("pilot ledger claims uncommitted success")
                if count >= max_new:
                    break
                preserve_interrupted(output, identifier)
                row = run_case(case, output, images, proof, timeout)
                stream.write(json.dumps(row, sort_keys=True) + "\n")
                prune_case(output, row, images, proof)
                count += 1
                print("V2_LOWDEPTH_7WAY_CASE", identifier,
                      "failed", [name for name in ASSEMBLERS
                                 if row["results"][name]["status"] != "success"],
                      flush=True)
        print("V2_LOWDEPTH_PILOT_COMPLETE_BATCH", count, "NOT_QUALIFIED")
        return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--source-attestation", type=Path, required=True)
    parser.add_argument("--fork", type=Path, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--max-new", type=int, default=1)
    args = parser.parse_args()
    images = json.loads(args.images.read_text())
    run(args.data, args.out, images, args.source_attestation,
        args.fork, args.base, timeout=args.timeout, max_new=args.max_new)


if __name__ == "__main__":
    main()
