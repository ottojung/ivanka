"""Prospective read-only lineage-preserving HXB2 low-depth repair cohort.

The original v1 corpus and every benchmark output remain immutable.
Only the read count of the 16 low_depth cases changes: quarter to half
normal depth. Every biological truth and all other read files are copied
byte-for-byte, never regenerated or modified.
"""
import json
from pathlib import Path
import shutil

from .hxb2_truth import haplotypes
from .synthetic import FAMILIES, fingerprint, generate_case

SCHEMA = "ivanka.expanded.cohort.hxb2.v2"
SOURCE = "ivanka.expanded.cohort.hxb2.v1"


def verify_metadata(root, cohort):
    if cohort.get("schema") != SCHEMA:
        raise ValueError("wrong low-depth cohort revision")
    seeds = cohort["seeds_per_family"]
    expected = [f"low_depth-s{i:03d}" for i in range(seeds)]
    if (cohort.get("changed_read_cases") != expected
            or cohort.get("source_cohort_schema") != SOURCE
            or cohort.get("new_low_depth_fraction") != "1/2"
            or cohort.get("old_low_depth_fraction") != "1/4"
            or not isinstance(cohort.get("source_cohort_sha256"), str)
            or len(cohort["source_cohort_sha256"]) != 64):
        raise ValueError("noncanonical v2 coverage revision")
    previous = cohort.get("unchanged_case_sha256")
    old_manifests = cohort.get("unchanged_manifest_sha256")
    if not isinstance(previous, dict) or not isinstance(old_manifests, dict):
        raise ValueError("missing unchanged case fingerprints")
    for case in cohort["cases"]:
        name = case["id"]
        if name in expected:
            continue
        if (previous.get(name) != case["sha256"]
                or old_manifests.get(name) != fingerprint(
                    Path(root) / name / "manifest.json")):
            raise ValueError("an unchanged synthetic case drifted")
    if (len(previous) != len(cohort["cases"]) - len(expected)
            or set(old_manifests) != set(previous)):
        raise ValueError("missing or excess unchanged case provenance")
    reference = next(x["id"] for x in cohort["cases"]
                     if x["id"].startswith("clonal-s"))
    normal = json.loads((Path(root) / reference / "manifest.json").read_text())["pairs"]
    for name in expected:
        record = json.loads((Path(root) / name / "manifest.json").read_text())
        if record["pairs"] != max(20, normal // 2):
            raise ValueError("v2 low-depth pair count not half normal")
    return True


def derive(source, destination):
    from .hxb2_cohort import verify_cohort
    source, destination = Path(source), Path(destination)
    old = json.loads((source / "cohort.json").read_text())
    if old.get("schema") != SOURCE or old.get("samples") != 25 * old["seeds_per_family"]:
        raise ValueError("v2 requires a verified original HXB2 cohort")
    parent_digest = verify_cohort(source, expected=old["samples"])
    normal = json.loads((source / "clonal-s000/manifest.json").read_text())["pairs"]
    if normal < 80 or normal % 4:
        raise ValueError("normal reference depth is not divisible by four")
    if destination.exists():
        raise FileExistsError("never overwrite any original or revised cohort")
    destination.mkdir(parents=True)
    modified = []
    inherited = {}
    inherited_manifests = {}
    generated = []
    for case in old["cases"]:
        name = case["id"]
        if name.startswith("low_depth-s"):
            seed = int(name.rsplit("-s", 1)[1])
            new = generate_case(destination, "low_depth", seed,
                                pairs=2 * normal, truth_model=haplotypes)
            prior = json.loads((source / name / "manifest.json").read_text())
            if new["sha256"][new["hidden_truth_file"]] != prior["sha256"][prior["hidden_truth_file"]]:
                raise ValueError("v2 must not change generating truth")
            modified.append(name)
            digest = new["sha256"]
        else:
            shutil.copytree(source / name, destination / name)
            digest = case["sha256"]
            inherited[name] = digest
            inherited_manifests[name] = fingerprint(
                source / name / "manifest.json")
        generated.append({"id": name, "sha256": digest})
    record = {"schema": SCHEMA, "samples": len(generated),
              "families": list(FAMILIES),
              "seeds_per_family": old["seeds_per_family"],
              "cases": generated, "changed_read_cases": modified,
              "old_low_depth_fraction": "1/4",
              "new_low_depth_fraction": "1/2",
              "source_cohort_schema": SOURCE,
              "source_cohort_sha256": parent_digest,
              "unchanged_case_sha256": inherited,
              "unchanged_manifest_sha256": inherited_manifests}
    (destination / "cohort.json").write_text(json.dumps(
        record, sort_keys=True, indent=2) + "\n")
    verify_metadata(destination, record)
    assert fingerprint(destination / "cohort.json") != parent_digest
    return record
