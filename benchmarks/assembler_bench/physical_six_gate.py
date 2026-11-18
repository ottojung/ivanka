"""Require real six original + eligible retry records before synthetic six."""
import argparse
import hashlib
import json
from pathlib import Path

SIX = ("iva", "haploflow", "megahit", "abyss", "spades", "velvet")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ready(root, images):
    root = Path(root)
    original = root / "phase-real198"
    retries = root / "phase-real198-memory-retries"
    origins = original / "run_manifest.json"
    done = original / "attempt_summary.json"
    outcome = retries / "attempt_summary.json"
    policy = retries / "resource_policy_receipt.json"
    if not all(p.is_file() for p in (origins, done, outcome, policy)):
        return False
    base = json.loads(origins.read_text())
    first = json.loads(done.read_text())
    final = json.loads(outcome.read_text())
    receipt = json.loads(policy.read_text())
    if (base.get("schema") != "ivanka.expanded.comparators_first_real.v1"
            or base.get("expected_samples") != 198
            or base.get("ivanka_deferred") is not True
            or set(base.get("images", {})) != set(SIX)
            or any(base["images"][t] != images[t] for t in SIX)
            or first.get("schema") != base["schema"]
            or first.get("samples") != 198
            or set(first.get("tools", ())) != set(SIX)
            or first.get("ivanka_deferred") is not True
            or first.get("manifest_sha256") != digest(origins)
            or final.get("schema") != "ivanka.expanded.physical-resource-retry.v1"
            or final.get("original") != str(original)
            or final.get("timeout_seconds") != 3000
            or final.get("finished") is not True
            or final.get("ivanka_deferred") is not True
            or receipt.get("schema") != final["schema"]
            or receipt.get("timeout_seconds") != 3000
            or receipt.get("concurrent_arms") != 2
            or receipt.get("do_not_rerun_original_successes") is not True
            or receipt.get("original_run_manifest_sha256") != digest(origins)
            or receipt.get("original_completed_summary_sha256") != digest(done)
            or set(receipt.get("eligibility", {})) != set(SIX)
            or final.get("eligible") != {
                t: len(receipt["eligibility"][t]) for t in SIX}):
        raise ValueError("physical source, image or recovery certificate drift")
    for tool in SIX:
        folder = original / tool / "checkpoints"
        if len(list(folder.glob("*.json"))) != 198:
            raise ValueError("original six physical checkpoints incomplete: " + tool)
        files = retries / tool / "checkpoints"
        eligible = receipt["eligibility"][tool]
        if len(list(files.glob("*.json"))) != len(eligible):
            raise ValueError("physical retries have missing checkpoints: " + tool)
        for sample in eligible:
            key = hashlib.sha256(sample.encode()).hexdigest() + ".json"
            record = json.loads((files / key).read_text())
            if (record.get("sample") != sample or record.get("tool") != tool
                    or record.get("image_id") != images[tool]
                    or record.get("arm", {}).get("image_id") != images[tool]
                    or record.get("original_checkpoint_sha256")
                    != digest(folder / key)
                    or record.get("resource_timeout_seconds") != 3000
                    or record["failed"] != (record["arm"]["exit_code"] != 0)
                    or not 0 <= record["arm"]["container_wall_seconds"] <= 3000.1):
                raise ValueError("invalid physical retry checkpoint: " + sample)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--images", required=True, type=Path)
    args = parser.parse_args()
    good = ready(args.root.resolve(), json.loads(args.images.read_text()))
    print("PHYSICAL_SIX_AND_RECOVERY_COMPLETE" if good else "PHYSICAL_SIX_PENDING")
    return 0 if good else 1


if __name__ == "__main__":
    raise SystemExit(main())
