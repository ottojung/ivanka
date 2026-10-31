"""Offline cross-invocation 198-sample diagnostic; never formal qualification."""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
from milestone198 import (MANIFEST_SHA256, PANEL_SHA256, SAMPLE_COUNT,
                          SCORE_FLOOR, SAMPLE_CAP_SECONDS, finite, psi)


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def pair(record, iva_id, ivanka_id):
    """Validate a recorded pair without altering its scientific source."""
    try:
        if record["status"] != "finished" or record["iva_baseline_reused"] is not True:
            return None, "unfinished_or_unverified_baseline"
        a, k, f = record["iva"], record["ivanka"], record["best_contig_acceptance"]
        if (a["exit_code"], k["exit_code"]) != (0, 0):
            return None, "arm_exit_failure"
        if (a["image_id"], k["image_id"]) != (iva_id, ivanka_id):
            return None, "image_id_mismatch"
        if "metrics" not in a or "metrics" not in k:
            return None, "missing_micall_metrics"
        if (f["method"] != "best_final_max_contig_local_alignment_over_reference_panel"
                or f["reference_panel_sha256"] != PANEL_SHA256
                or f["reference_count"] != 33):
            return None, "wrong_alignment_panel"
        sa, sk, ta, tk = f["iva_score"], f["ivanka_score"], a["seconds"], k["seconds"]
        if not all(finite(x, positive=True) for x in (sa, ta, tk)) or not finite(sk):
            return None, "nonfinite_score_or_runtime"
        if sk < SCORE_FLOOR * sa:
            return None, "below_strict_90_percent_floor"
        if (not finite(record["total_seconds"]) or
                record["total_seconds"] < 0 or
                record["total_seconds"] > SAMPLE_CAP_SECONDS or
                tk > SAMPLE_CAP_SECONDS or
                record["sample_time_limit_seconds"] != SAMPLE_CAP_SECONDS):
            return None, "runtime_limit"
        provenance = record["provenance"]
        if (provenance["iva_image_id"] != iva_id or
                len(provenance["fastq_sha256"]) != 2 or
                not all(isinstance(x, str) and len(x) == 64 and
                        all(c in "0123456789abcdef" for c in x)
                        for x in provenance["fastq_sha256"])):
            return None, "input_provenance"
        corrected = False
        if record["failed"] is not False or f["pass"] is not True:
            old_floor = f["threshold"]
            if not (record["failed"] is True and f["pass"] is False and
                    finite(old_floor) and old_floor > SCORE_FLOOR and
                    sk < old_floor * sa and
                    not any(key.endswith("_error") for key in record)):
                return None, "unexplained_failure"
            corrected = True
        return (sk - sa, ta - tk, corrected), None
    except (KeyError, ValueError, TypeError):
        return None, "malformed_record"


def audit(paths, manifest):
    if sha(manifest) != MANIFEST_SHA256:
        raise ValueError("Frozen manifest SHA256 mismatch")
    with manifest.open() as source:
        names = [row["sample"] for row in csv.DictReader(source, delimiter="\t")]
    if len(names) != SAMPLE_COUNT or len(set(names)) != SAMPLE_COUNT:
        raise ValueError("Frozen cohort is not 198 unique samples")
    records, invocations, hashes = [], [], {}
    for path in paths:
        hashes[str(path)] = sha(path)
        with path.open() as source:
            finished = [r for line in source if line.strip()
                        if (r := json.loads(line)).get("status") == "finished"]
        ids = {r.get("invocation") for r in finished}
        if len(ids) != 1 or None in ids:
            raise ValueError("Each source must contain one pinned invocation")
        invocations.extend(ids)
        records.extend(finished)
    samples = collections.Counter(r.get("sample") for r in records)
    if len(records) != SAMPLE_COUNT or set(samples) != set(names) or max(samples.values()) != 1:
        raise ValueError("Completed records do not match exact frozen cohort")
    a_ids = {r.get("iva", {}).get("image_id") for r in records}
    k_ids = {r.get("ivanka", {}).get("image_id") for r in records}
    if len(a_ids) != 1 or len(k_ids) != 1 or None in a_ids | k_ids:
        raise ValueError("Mixed MiCall image IDs")
    a_id, k_id = next(iter(a_ids)), next(iter(k_ids))
    score, runtime, errors, corrected = [], [], {}, []
    projects = collections.defaultdict(list)
    for r in records:
        values, error = pair(r, a_id, k_id)
        if error:
            errors[r["sample"]] = error
            continue
        ds, dt, legacy = values
        score.append(ds)
        runtime.append(dt)
        projects[r["provenance"]["micall_project_code"]].append(dt)
        if legacy:
            corrected.append(r["sample"])
    valid = len(score) == SAMPLE_COUNT
    result = {
        "kind": "cross_invocation_offline_diagnostic_not_formal",
        "formal_qualification_pass": False,
        "source_results_sha256": hashes,
        "source_invocations": sorted(invocations),
        "manifest_sha256": MANIFEST_SHA256,
        "reference_panel_sha256": PANEL_SHA256,
        "iva_image_id": a_id,
        "ivanka_image_id": k_id,
        "completed_samples": len(records),
        "strict_score_runtime_valid_pairs": len(score),
        "errors": errors,
        "legacy_95_percent_flags_reinterpreted": sorted(corrected),
        "runtime_by_project": {k: {"samples": len(v),
            "mean_iva_minus_ivanka_seconds": sum(v)/len(v)}
            for k, v in sorted(projects.items())},
        "score_psi": psi(score) if valid else None,
        "runtime_psi": psi(runtime) if valid else None,
    }
    result["all_six_psi_positive"] = valid and all(
        result[metric][power] > 0 for metric in ("score_psi", "runtime_psi")
        for power in ("psi0", "psi1", "psi2"))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--results", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() in {p.resolve() for p in args.results}:
        raise ValueError("Output cannot overwrite a source")
    result = audit(args.results, args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    args.output.chmod(0o600)
    print(json.dumps({k: result[k] for k in ("completed_samples",
        "strict_score_runtime_valid_pairs", "all_six_psi_positive",
        "score_psi", "runtime_psi")}, sort_keys=True))


if __name__ == "__main__":
    main()
