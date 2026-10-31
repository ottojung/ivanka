"""Read pinned source records; reinterpret only legacy 95% score flags."""
import hashlib
import json
from milestone198 import SCORE_FLOOR


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def reinterpret(record):
    provenance = record["provenance"]
    hashes = provenance["fastq_sha256"]
    if provenance["iva_image_id"] != record["iva"]["image_id"] or len(hashes) != 2 or not all(isinstance(h, str) and len(h) == 64 for h in hashes):
        raise ValueError("Invalid recorded input provenance")
    final = record["best_contig_acceptance"]
    if record["failed"] is False and final["pass"] is True:
        return record, False
    a, b, old = final["iva_score"], final["ivanka_score"], final["threshold"]
    if not (record["failed"] is True and final["pass"] is False
            and isinstance(old, (int, float)) and old > SCORE_FLOOR
            and a > 0 and SCORE_FLOOR*a <= b < old*a
            and record["status"] == "finished"
            and record["iva"]["exit_code"] == record["ivanka"]["exit_code"] == 0
            and not any(k.endswith("_error") for k in record)):
        raise ValueError("Unexplained original failure: " + record["sample"])
    return dict(record, failed=False, best_contig_acceptance=dict(
        final, **{"pass": True, "threshold": SCORE_FLOOR})), True


def load_sources(paths):
    records, invocations, hashes = [], [], {}
    for path in paths:
        hashes[str(path)] = sha(path)
        with path.open() as source:
            rows = [r for line in source if line.strip()
                    if (r := json.loads(line)).get("status") == "finished"]
        ids = {r.get("invocation") for r in rows}
        if len(ids) != 1 or None in ids:
            raise ValueError("Source does not have one pinned invocation")
        records.extend(rows)
        invocations.extend(ids)
    return records, invocations, hashes
