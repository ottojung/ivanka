"""Source-attested synthetic comparator stage before all deferred Ivanka runs.

Use the original frozen synthetic runner as a library, without modifying it.
Write six-arm per-case evidence alongside the original seven-arm checkpoints.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path

from expanded.adapters import ASSEMBLERS
from expanded.fork_micall_synthetic import checked_images, manifest
from expanded.hxb2_cohort import attestation
from expanded.micall_checkpoint import digest, existing_case, identity, reusable_arm
from expanded.micall_dominant import SCORE_ORIGIN, MULTITRUTH_SCORE_ORIGIN
from expanded.micall_lock import exclusive_lock
from expanded.micall_synthetic import attempt
from expanded.run_synthetic import cohort_rows
from expanded.synthetic import ACTIVE_FAMILIES

SIX = tuple(name for name in ASSEMBLERS if name != "ivanka")
SCHEMA = "ivanka.synthetic.six-before-ivanka.v1"
SUMMARY = "six_comparators_summary.json"
SOURCE = Path(__file__).resolve()


def score_origin_for(case_manifest):
    return (MULTITRUTH_SCORE_ORIGIN if case_manifest.get("score_model_revision") == 2
            else SCORE_ORIGIN)


def arm_records(folder, images, score_origin):
    records = {}
    for tool in SIX:
        record = reusable_arm(folder / tool, tool, images[tool], score_origin)
        if record is None:
            return None
        records[tool] = record
    return records


def sidecar(folder, fields, records, manifest_sha):
    return {
        "schema": SCHEMA,
        "identity": fields,
        "manifest_sha256": manifest_sha,
        "stage_source_sha256": digest(SOURCE),
        "arms_sha256": {
            tool: digest(folder / tool / "execution.json") for tool in SIX
        },
        "statuses": {tool: records[tool]["status"] for tool in SIX},
        "qualification": "INCOMPLETE_UNTIL_IVANKA",
    }


def verify_case(folder, fields, images, score_origin, manifest_sha):
    proof = folder / "six_arms.json"
    if not proof.is_file():
        return None
    records = arm_records(folder, images, score_origin)
    if records is None:
        raise ValueError("six-arm certificate lacks original arm evidence: " + str(folder))
    actual = sidecar(folder, fields, records, manifest_sha)
    if json.loads(proof.read_text()) != actual:
        raise ValueError("six-arm checkpoint modified: " + str(folder))
    return actual


def save_json(path, obj):
    temporary = path.with_suffix(path.suffix + ".partial")
    if path.exists():
        raise FileExistsError("would overwrite existing checkpoint " + str(path))
    if temporary.exists():
        # A previous crash may leave incomplete JSON. Preserve, never discard it.
        for n in range(1, 1000):
            archived = temporary.with_name(temporary.name + f".interrupted-{n:03d}")
            if not archived.exists():
                temporary.rename(archived)
                break
        else:
            raise ValueError("too many interrupted checkpoint temp files")
    with temporary.open("x") as stream:
        json.dump(obj, stream, sort_keys=True, indent=2)
        stream.write("\n")
    temporary.replace(path)


def run_one(row, root, images, truth, manifest_sha):
    identifier, _, case_manifest = row
    folder = root / identifier
    fields = identity(identifier, case_manifest, truth)
    score_origin = score_origin_for(case_manifest)
    old = verify_case(folder, fields, images, score_origin, manifest_sha)
    if old is not None:
        return identifier, old
    if (folder / "matrix.json").exists():
        existing_case(folder, fields, images)  # Reject altered seven-arm results.
    folder.mkdir(exist_ok=True)
    for tool in SIX:
        dest = folder / tool
        if reusable_arm(dest, tool, images[tool], score_origin) is not None:
            continue
        if dest.exists():
            interrupted = folder / "_interrupted"
            interrupted.mkdir(exist_ok=True)
            for n in range(1, 1000):
                target = interrupted / f"{tool}-{n:03d}"
                if not target.exists():
                    dest.rename(target)
                    break
            else:
                raise ValueError("too many interrupted six-arm attempts")
        result = attempt((row[1], case_manifest), dest, tool, images[tool], 3000)
        if reusable_arm(dest, tool, images[tool], score_origin) != result:
            raise ValueError("new six-arm evidence does not independently verify")
    records = arm_records(folder, images, score_origin)
    if records is None:
        raise ValueError("missing one of six comparator outcomes")
    proof = sidecar(folder, fields, records, manifest_sha)
    save_json(folder / "six_arms.json", proof)
    if verify_case(folder, fields, images, score_origin, manifest_sha) != proof:
        raise ValueError("six-arm certificate failed independent recheck")
    return identifier, proof


def verify_all(rows, root, images, truth, manifest_sha):
    hashes = {}
    failures = 0
    for identifier, _, case_manifest in rows:
        folder = root / identifier
        fields = identity(identifier, case_manifest, truth)
        proof = verify_case(
            folder, fields, images, score_origin_for(case_manifest), manifest_sha)
        if proof is None:
            raise ValueError("missing six-comparator case " + identifier)
        hashes[identifier] = digest(folder / "six_arms.json")
        failures += sum(status != "success" for status in proof["statuses"].values())
    return {
        "schema": SCHEMA, "cases": len(rows), "tools_per_case": 6,
        "source_manifest_sha256": manifest_sha,
        "stage_source_sha256": digest(SOURCE),
        "case_checkpoints_sha256": hashes,
        "failed_comparator_arms": failures,
        "status": "SIX_TERMINAL_IVANKA_DEFERRED",
    }


def run(data, root, images, fork, base, attestation_file, jobs=2):
    if not 1 <= jobs <= 2:
        raise ValueError("only the independently bounded 1-2 worker recovery mode is allowed")
    rows = list(cohort_rows(data))
    if len(rows) != len(ACTIVE_FAMILIES) * 16:
        raise ValueError("not exactly the frozen 464 synthetic cases")
    truth = attestation(data, expected=464)
    checked_images(images, attestation_file, fork, base)
    original = root / "run_manifest.json"
    if not original.is_file() or json.loads(original.read_text()) != manifest(
            data, truth, images, attestation_file, None):
        raise ValueError("original seven-image synthetic source manifest changed")
    manifest_sha = digest(original)
    with exclusive_lock(root):
        completed = 0
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = [
                pool.submit(run_one, row, root, images, truth, manifest_sha)
                for row in rows
            ]
            for future in as_completed(futures):
                identifier, proof = future.result()
                completed += 1
                print("SYNTHETIC_SIX_COMPARATORS", completed, "/464", identifier,
                      "failed", [t for t, v in proof["statuses"].items()
                                 if v != "success"], flush=True)
        summary = verify_all(rows, root, images, truth, manifest_sha)
        target = root / SUMMARY
        if target.exists():
            if json.loads(target.read_text()) != summary:
                raise ValueError("six-comparator summary differs from source checkpoints")
        else:
            save_json(target, summary)
        return summary


def verify_existing(root, images):
    """Verify completed six-arm proof using original manifest identities."""
    original = root / "run_manifest.json"
    summary_file = root / SUMMARY
    if not original.is_file() or not summary_file.is_file():
        return False
    frozen = json.loads(original.read_text())
    summary = json.loads(summary_file.read_text())
    if (summary.get("schema") != SCHEMA or summary.get("cases") != 464
            or summary.get("tools_per_case") != 6
            or summary.get("source_manifest_sha256") != digest(original)
            or summary.get("stage_source_sha256") != digest(SOURCE)
            or frozen.get("images") != images
            or len(summary.get("case_checkpoints_sha256", {})) != 464):
        return False
    failures = 0
    for identifier, expected in summary["case_checkpoints_sha256"].items():
        folder = root / identifier
        proof = folder / "six_arms.json"
        if digest(proof) != expected:
            raise ValueError("six-stage checkpoint content changed: " + identifier)
        data = json.loads(proof.read_text())
        if (data.get("schema") != SCHEMA or data.get("manifest_sha256") != digest(original)
                or data.get("stage_source_sha256") != digest(SOURCE)
                or data.get("identity", {}).get("id") != identifier
                or set(data.get("statuses", {})) != set(SIX)
                or set(data.get("arms_sha256", {})) != set(SIX)):
            raise ValueError("invalid six-stage case certificate: " + identifier)
        version = frozen["truth_proof"].get("schema")
        score_origin = (MULTITRUTH_SCORE_ORIGIN
                        if version == "ivanka.mixed_viral_truth_validation.v4"
                        else SCORE_ORIGIN)
        records = arm_records(folder, images, score_origin)
        if records is None or sidecar(
                folder, data["identity"], records, digest(original)) != data:
            raise ValueError("missing or altered six-stage arm evidence: " + identifier)
        failures += sum(v != "success" for v in data["statuses"].values())
    if failures != summary.get("failed_comparator_arms"):
        raise ValueError("six-stage failure count changed")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--images", required=True, type=Path)
    parser.add_argument("--check-complete", action="store_true")
    parser.add_argument("--data", type=Path)
    parser.add_argument("--fork", type=Path)
    parser.add_argument("--base")
    parser.add_argument("--attestation", type=Path)
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    images = json.loads(args.images.read_text())
    if args.check_complete:
        done = verify_existing(args.out, images)
        print("SYNTHETIC_SIX_COMPLETE" if done else "SYNTHETIC_SIX_PENDING")
        return 0 if done else 1
    if not all((args.data, args.fork, args.base, args.attestation)):
        parser.error("six-comparator execution requires original frozen source")
    outcome = run(args.data, args.out, images, args.fork, args.base,
                  args.attestation, args.jobs)
    print("SYNTHETIC_SIX_TERMINAL", outcome["cases"],
          "failed_arms", outcome["failed_comparator_arms"])


if __name__ == "__main__":
    raise SystemExit(main())
