"""Preserve each physical MiCall comparison with its own fresh IVA controls."""
import csv
import json
from pathlib import Path

from benchmarks.milestone198 import PANEL_SHA256
from .archive_sources import TOOLS, digest, run_template
from .real_public import measured


def aliases_for(data):
    with (Path(data)/"manifest.tsv").open(newline="") as stream:
        rows=list(csv.DictReader(stream, delimiter="\t"))
    if len(rows) != 198 or len({r["sample"] for r in rows}) != 198:
        raise ValueError("physical sample manifest is not the pinned cohort")
    return {r["sample"]:f"R{i:03d}" for i,r in
            enumerate(sorted(rows,key=lambda r:r["sample"]),1)}


def recover(root, data, attestation, candidate, identifier, title):
    root=Path(root)
    manifest_file=root/"run_manifest.json"
    manifest=json.loads(manifest_file.read_text())
    if (manifest.get("schema") != "ivanka.expanded.fork_micall_real.v1"
            or manifest.get("expected_samples") != 198
            or manifest.get("selected_sample") is not None
            or candidate not in manifest.get("selected_tools",[])):
        raise ValueError("physical run not an original full-cohort attempt")
    aliases=aliases_for(data)
    events_file=root/candidate/"results.jsonl"
    if not events_file.is_file():
        raise ValueError("physical run has no sample results")
    seen, starts, finished=set(),set(),[]
    for line in events_file.read_text().splitlines():
        if not line.strip():
            continue
        event=json.loads(line)
        sample=event.get("sample")
        status=event.get("status")
        if sample not in aliases or status not in ("started","finished"):
            raise ValueError("foreign physical sample or event")
        if status=="started":
            if sample in starts:
                raise ValueError("duplicated physical sample start")
            starts.add(sample)
            continue
        if sample not in starts or sample in seen:
            raise ValueError("duplicated or unmatched physical result")
        seen.add(sample)
        if (event.get("iva",{}).get("image_id")!=manifest["images"]["iva"]
                or event.get("ivanka",{}).get("image_id")
                !=manifest["images"][candidate]):
            raise ValueError("physical MiCall result uses different image")
        claim=event.get("best_contig_acceptance") or {}
        if claim:
            if (claim.get("method") !=
                    "best_final_max_contig_local_alignment_over_reference_panel"
                    or claim.get("reference_count") != 33
                    or claim.get("reference_panel_sha256") != PANEL_SHA256):
                raise ValueError("physical score method/panel mismatch")
        elif not event.get("failed") or all(
                event[arm].get("exit_code") == 0
                for arm in ("iva","ivanka")):
            raise ValueError("unexplained missing physical alignment score")
        values, timings, missing, sources={}, {}, [], {}
        for arm, name in (("iva","iva"),("ivanka",candidate)):
            score, sec=measured(event,arm)
            if event[arm].get("exit_code") != 0:
                missing.append(name)
            if (sec is None and event[arm].get("exit_code") == 0
                    and event[arm].get("timing_origin")
                    == "micall_in_container_monotonic_v1"):
                sec = event[arm].get("seconds")
            values[name],timings[name]=score,sec
            location=Path(event[arm].get("artifact_dir") or "")
            path=location/"conseq.csv"
            sources[name]=digest(path) if path.is_file() else None
        score={name:values.get(name) for name in TOOLS}
        seconds={name:timings.get(name) for name in TOOLS}
        sha={name:sources.get(name) for name in TOOLS}
        finished.append({
            "alias":aliases[sample], "score":score, "seconds":seconds,
            "failures":missing, "floor_ok":None,
            "outcome":"failure" if missing else "incomplete",
            "source_sha256":sha,
        })
    finished.sort(key=lambda r:r["alias"])
    run=run_template(identifier,title,"real",finished,manifest["images"],
                     attestation,manifest_file,events_file)
    run["archive"]["original_candidate"]=candidate
    return run
