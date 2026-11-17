"""Derive new 464-case inputs from attested unchanged 400-case reads."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile

from .hxb2_cohort import attestation, verify_cohort
from .synthetic import (
    ACTIVE_FAMILIES, FAMILIES, MIXED_FAMILIES,
    fingerprint, generate_case, generate_cohort,
)


def compare_generation(source, normal_pairs):
    """Reject reuse if v6 changed any legacy paired FASTQ or its truth."""
    with tempfile.TemporaryDirectory() as temporary:
        for family in FAMILIES:
            fresh = generate_case(temporary, family, 0, normal_pairs)
            original = json.loads(
                (source / f"{family}-s000/manifest.json").read_text())
            if fresh["sha256"] != original["sha256"]:
                raise ValueError(f"{family}: v6 reads/truth differ from v5")


def derive(source, destination, *, seeds=16, normal_pairs=10000):
    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise FileExistsError("new source cohort must not overwrite another")
    if seeds != 16 or normal_pairs != 10000:
        raise ValueError("canonical v6 derivation requires 16 seeds and 10k pairs")
    old = json.loads((source / "cohort.json").read_text())
    if (old.get("schema") != "ivanka.expanded.cohort.hxb2.v3"
            or old.get("seeds_per_family") != 16
            or old.get("split") != "development"
            or old.get("normal_pairs") != normal_pairs):
        raise ValueError("requires immutable versioned 400-case v5 source")
    certificate = attestation(source, expected=400)
    compare_generation(source, normal_pairs)
    destination.mkdir(parents=True)
    cases = []
    for family in FAMILIES:
        for seed in range(seeds):
            identifier = f"{family}-s{seed:03d}"
            src, dest = source / identifier, destination / identifier
            shutil.copytree(src, dest)
            manifest_file = dest / "manifest.json"
            meta = json.loads(manifest_file.read_text())
            meta["score_model_revision"] = 2
            manifest_file.write_text(json.dumps(meta, sort_keys=True,
                                                indent=2) + "\n")
            cases.append({"id": identifier, "sha256": meta["sha256"]})
    for family in MIXED_FAMILIES:
        for seed in range(seeds):
            meta = generate_case(destination, family, seed, normal_pairs)
            cases.append({"id": f"{family}-s{seed:03d}",
                          "sha256": meta["sha256"]})
    cohort = {
        "schema": "ivanka.expanded.cohort.hxb2.v4",
        "families": list(ACTIVE_FAMILIES),
        "seeds_per_family": seeds,
        "samples": len(cases), "seed_start": 0, "split": "development",
        "normal_pairs": normal_pairs, "cases": cases,
        "quality_profile_sha256": old["quality_profile_sha256"],
    }
    pending = destination / "cohort.json.pending"
    with pending.open("x") as stream:
        json.dump(cohort, stream, sort_keys=True, indent=2)
        stream.write("\n")
    pending.replace(destination / "cohort.json")
    verify_cohort(destination, expected=len(ACTIVE_FAMILIES) * seeds)
    return certificate, attestation(destination, expected=len(cases))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--certificate", type=Path, required=True)
    args = parser.parse_args()
    original, new = derive(args.source, args.destination)
    with args.certificate.open("x") as stream:
        json.dump({"schema": "ivanka.synthetic.v6_derivation.v1",
                   "original": original, "replacement": new},
                  stream, sort_keys=True, indent=2)
        stream.write("\n")
    print("MIXED_VIRAL_COHORT_DERIVED", new["samples_validated"],
          new["cohort_sha256"])


if __name__ == "__main__":
    main()
