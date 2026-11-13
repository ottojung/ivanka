"""Rescore retained HXB2 final MiCall outputs with durable per-case records."""
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path

from benchmarks.expanded.micall_checkpoint import identity
from benchmarks.expanded.micall_dominant import evaluate_final_alignment
from .archive_sources import (
    TOOLS, digest, diagnostics_from_execution, run_template)
from .hxb2_preview import pinned_truth, COHORT_SHA


def _case(args):
    root, data, images, proof, row, alias, cache, method = args
    root, data, cache = Path(root), Path(data), Path(cache)
    case = row["id"]
    details = data / case
    synthetic = json.loads((details / "manifest.json").read_text())
    expected = identity(case, {
        "family": row["family"], "sha256": synthetic["sha256"]}, proof)
    if (any(row.get(key) != value for key, value in expected.items())
            or set(row["results"]) != set(TOOLS)):
        raise ValueError("synthetic truth and read identities differ")
    source_dir = root / case
    input_digest = hashlib.sha256(json.dumps(
        {"execution": row, "method_sha256": method},
        sort_keys=True).encode()).hexdigest()
    cache_file = cache / (case + ".json")
    if cache_file.is_file():
        stored = json.loads(cache_file.read_text())
        output = stored.get("sample")
        if stored.get("input_digest") == input_digest and output:
            if all(output["source_sha256"].get(tool) == (
                    digest(source_dir / tool / "conseq.csv")
                    if (source_dir / tool / "conseq.csv").is_file() else None)
                   for tool in TOOLS):
                return output
    scores, timings, failures, sha256s, metrics = {}, {}, [], {}, {}
    scoring_cache = {}
    for name in TOOLS:
        part = row["results"][name]
        directory = source_dir / name
        if (part.get("sha256") != images[name]
                or json.loads((directory / "execution.json").read_text())
                != part):
            raise ValueError("archived MiCall execution was changed")
        source = part.get("final_dominant", {})
        filename = source.get("source_output")
        if part["status"] == "success" and (
                not filename or not (directory / filename).is_file()
                or digest(directory / filename)
                != source.get("conseq_csv_sha256")):
            raise ValueError("original final MiCall evidence altered")
        if part["status"] != "success":
            failures.append(name)
            scores[name], timings[name], sha256s[name] = None, None, None
            continue
        seconds = part.get("seconds")
        if (part.get("exit_code") != 0
                or part.get("timing_origin")
                != "micall_in_container_monotonic_v1"
                or type(seconds) not in (float, int)
                or not math.isfinite(seconds) or not 0 < seconds <= 1800):
            raise ValueError("untrustworthy original MiCall timer")
        final = directory / "conseq.csv"
        sha256s[name] = digest(final) if final.is_file() else None
        if sha256s[name] is not None:
            if sha256s[name] not in scoring_cache:
                value = evaluate_final_alignment(
                    synthetic, details / synthetic["hidden_truth_file"],
                    directory)
                scoring_cache[sha256s[name]] = value["score"]
            scores[name] = scoring_cache[sha256s[name]]
        else:
            scores[name] = None
        timings[name] = float(seconds)
        metrics[name] = diagnostics_from_execution(part)
    complete = not failures and all(scores[name] is not None
                                    for name in TOOLS)
    highest = max(scores[name] for name in TOOLS if name != "ivanka"
                  ) if complete else None
    sample = {
        "alias": alias, "family": row["family"],
        "score": scores, "seconds": timings,
        "failures": failures,
        "floor_ok": scores["ivanka"] >= .9*highest if complete else None,
        "outcome": "failure" if failures else
        "success" if complete else "incomplete",
        "source_sha256": sha256s, "diagnostics": metrics,
    }
    cache.mkdir(parents=True, exist_ok=True)
    pending = cache / (case + "." + str(os.getpid()) + ".pending")
    pending.write_text(json.dumps(
        {"input_digest": input_digest, "sample": sample},
        sort_keys=True, separators=(",", ":")) + "\n")
    pending.replace(cache_file)
    return sample


def recover(root, data, attestation, identifier, title, cache_directory=None):
    root, data = Path(root), Path(data)
    manifest_file = root / "run_manifest.json"
    manifest = json.loads(manifest_file.read_text())
    cohort, proof = pinned_truth()
    if (manifest.get("schema") != "ivanka.expanded.fork_micall_synthetic.v1"
            or manifest.get("cohort_sha256") != COHORT_SHA
            or manifest.get("truth_proof") != proof
            or manifest.get("expected") != 400
            or manifest.get("limit") is not None
            or manifest.get("qualified") is not False):
        raise ValueError("archived synthetic run does not match frozen HXB2")
    rows_file = root / "results.jsonl"
    rows = [json.loads(line) for line in rows_file.read_text().splitlines()
            if line.strip()]
    identities = {entry["id"]: entry for entry in cohort["cases"]}
    aliases = {name: f"H{i:03d}" for i, name in enumerate(
        sorted(identities), start=1)}
    if (len(rows) != len({row["id"] for row in rows})
            or any(row["id"] not in identities for row in rows)):
        raise ValueError("archived synthetic case is duplicated or foreign")
    method = hashlib.sha256("".join(digest(path) for path in (
        Path(__file__).with_name("archive_synthetic.py"),
        Path(__file__).parents[1] / "reference_panel.py",
        Path(__file__).parents[1] / "project_references.py",
        Path(__file__).parents[1] / "expanded/micall_dominant.py",
    )).encode()).hexdigest()
    cache = (Path(cache_directory) if cache_directory
             else root / ".rescored-cases") / identifier
    jobs = [(root, data, manifest["images"], proof, row,
             aliases[row["id"]], cache, method)
            for row in sorted(rows, key=lambda x:x["id"])]
    workers = max(1, min(4, int(os.environ.get("IVANKA_ARCHIVE_WORKERS", "3"))))
    with ProcessPoolExecutor(max_workers=workers) as executor:
        samples = list(executor.map(_case, jobs))
    result = run_template(identifier, title, "synthetic", samples,
                          manifest["images"], attestation,
                          manifest_file, rows_file)
    result["hxb2_truth_verified"] = True
    result["cohort_manifest_sha256"] = COHORT_SHA
    result["reference_manifest_sha256"] = proof["reference_manifest_sha256"]
    return result
