"""Format source-attested physical-198 checkpoints without sample identifiers."""
import csv
import json
import math
from pathlib import Path

from benchmarks.expanded.adapters import ASSEMBLERS
from .real_progress import snapshot
from .hxb2_preview import sha

ID = "real198-fork-source-attested-live"
TOOLS = list(ASSEMBLERS)
RUN_SCHEMA = "ivanka.assembler-bench.public.v1"


def sample_aliases(data):
    with (Path(data) / "manifest.tsv").open(newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    return {row["sample"]: f"R{i:03d}"
            for i, row in enumerate(sorted(rows, key=lambda r: r["sample"]), 1)}


def measured(event, name):
    """Keep scored floor failures; only unscored failed arms are unavailable."""
    if type(event.get("failed")) is not bool:
        raise ValueError("real MiCall checkpoint lacks boolean failure outcome")
    arm = event[name]
    acceptance = event.get("best_contig_acceptance") or {}
    score = acceptance.get(
        "iva_score" if name == "iva" else "ivanka_score")
    seconds = arm.get("seconds")
    ok = (arm.get("exit_code") == 0
          and arm.get("timing_origin") == "micall_in_container_monotonic_v1")
    if (score is None or seconds is None or not ok):
        if event["failed"] and (score is None or not ok):
            return None, None
        raise ValueError("successful MiCall arm has missing score or timer")
    if (type(score) not in (int, float)
            or type(seconds) not in (int, float)
            or not math.isfinite(score) or score < 0
            or not math.isfinite(seconds) or not 0 < seconds <= 1800):
        raise ValueError("real MiCall finished result lacks valid score or time")
    return float(score), float(seconds)


def case_rows(root, data, images):
    aliases = sample_aliases(data)
    cases = {name: {} for name in TOOLS}
    failures = {name: set() for name in TOOLS}
    for name in TOOLS:
        if name == "iva":
            continue
        path = Path(root) / name / "results.jsonl"
        if not path.is_file():
            continue
        started = set()
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            case = event.get("sample")
            if case not in aliases or event.get("status") not in ("started", "finished"):
                raise ValueError("unexpected physical-198 sample or event")
            if event["status"] == "started":
                if case in started:
                    raise ValueError("duplicate physical case start")
                started.add(case)
                continue
            if case not in started or case in cases[name]:
                raise ValueError("physical result not a unique completed case")
            if (event["iva"].get("image_id") != images["iva"]
                    or event["ivanka"].get("image_id") != images[name]):
                raise ValueError("physical result uses unexpected MiCall image")
            cases[name][case] = measured(event, "ivanka")
            if cases[name][case][0] is None:
                failures[name].add(case)
            iva = measured(event, "iva")
            if case not in cases["iva"]:
                cases["iva"][case] = iva
                if iva[0] is None:
                    failures["iva"].add(case)
    return aliases, cases, failures


def preview(root, data, runner, attestation, base, images, fork_provenance):
    """Verify the same immutable checkpoint manifest as the public counters."""
    proof = snapshot(root, data, runner, attestation, base, images)
    aliases, cases, failures = case_rows(root, data, images)
    observed = set().union(*(set(rows) for rows in cases.values()))
    samples = []
    for case in sorted(observed, key=aliases.get):
        score = {name: cases[name].get(case, (None, None))[0] for name in TOOLS}
        seconds = {name: cases[name].get(case, (None, None))[1] for name in TOOLS}
        missing = [name for name in TOOLS if case in failures[name]]
        other = [score[name] for name in TOOLS if name != "ivanka"
                 and score[name] is not None]
        floor = (score["ivanka"] >= .9 * max(other)
                 if score["ivanka"] is not None and len(other) == len(TOOLS)-1
                 and not missing else None)
        samples.append({"alias": aliases[case], "score": score,
                        "seconds": seconds, "failures": missing,
                        "floor_ok": floor,
                        "outcome": "failure" if missing else
                        "success" if all(x is not None for x in score.values())
                        else "incomplete"})
    if any(len(cases[name]) != proof["candidates"][name]["finished"]
           for name in proof["candidates"]):
        raise ValueError("physical candidate counters disagree with result rows")
    return {
        "schema": RUN_SCHEMA, "id": ID,
        "title": "198 physical samples · source-attested seven-way MiCall",
        "date": "2026-11-13", "cohort": "real", "status": "incomplete",
        "expanded_status": "incomplete", "eligible_for_expanded": False,
        "expected_sample_count": 198, "sample_count": len(samples),
        "tools": TOOLS, "images": images, "samples": samples, "psi": {},
        "source_manifest_sha256": sha(Path(root) / "run_manifest.json"),
        "status_reason": ("Source-attested MiCall comparison of all seven "
                          "assemblers on the same 198 physical samples. "
                          "Only completed case-arm pairs count; not qualified."),
        "micall_fork_provenance": fork_provenance,
        "physical_progress": proof["candidates"],
    }
