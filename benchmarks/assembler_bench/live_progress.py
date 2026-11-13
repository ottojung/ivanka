"""Publish monotonically growing, source-verified partial benchmark snapshots."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile

from .fork_progress import preview as fork_preview, checked as checked_fork
from .current_mapping import snapshot as mapping_snapshot
from .real_public import preview as physical_preview
from .combined_public import preview as combined_preview
from .public_dominance import enrich
from .real_progress import snapshot as real_snapshot
from .site_build import SITE, validate_public_site

FORK_ID = "hxb2-v4-fork-source-attested-live"


def replace_run(runs, report):
    """Stable run IDs preserve bookmarked URLs across new checkpoints."""
    existing = next((r for r in runs if r["id"] == report["id"]), None)
    if existing:
        if report["sample_count"] < existing["sample_count"]:
            raise ValueError("live benchmark checkpoint count regressed")
        if report["images"] != existing["images"]:
            raise ValueError("live benchmark changed assembler images")
    return [r for r in runs if r["id"] != report["id"]] + [report]


def update(site, fork, fork_runner, attestation, fork_repo, base,
           *, real=None, real_data=None):
    site = Path(site)
    target = site / "data/runs.json"
    public = json.loads(target.read_text())
    fork_run = fork_preview(fork, fork_runner, attestation, fork_repo, base)
    public["runs"] = [fork_run]
    if real is not None:
        if real_data is None:
            raise ValueError("real benchmark requires frozen input manifest")
        prior = public.get("real_progress", {}).get("candidates", {})
        snapshot = real_snapshot(
            real, real_data, fork_runner, attestation, base,
            fork_run["images"])
        for name, result in snapshot["candidates"].items():
            if result["finished"] < prior.get(name, {}).get("finished", 0):
                raise ValueError("physical-198 finished case count regressed")
        public["real_progress"] = snapshot
        physical = physical_preview(real, real_data, fork_runner,
                                    attestation, base, fork_run["images"],
                                    fork_run["micall_fork_provenance"])
        public["runs"].append(physical)
        public["runs"].append(combined_preview(fork_run, physical))
    public = enrich(public)
    _, rows, _, _ = checked_fork(fork, fork_runner, attestation,
                                fork_repo, base)
    diagnostics = mapping_snapshot(rows, fork_run)
    with tempfile.TemporaryDirectory(prefix="bench-live-") as folder:
        staged = Path(folder) / "site"
        shutil.copytree(site, staged)
        shutil.copy2(attestation, staged / "data/live-fork-attestation.json")
        (staged / "data/runs.json").write_text(
            json.dumps(public, sort_keys=True, indent=2) + "\n")
        (staged / "data/mapping-diagnostics.json").write_text(
            json.dumps(diagnostics, sort_keys=True, indent=2) + "\n")
        validate_public_site(staged)
        staged_file = staged / "data/runs.json"
        target_diagnostics = site / "data/mapping-diagnostics.json"
        staged_diagnostics = staged / "data/mapping-diagnostics.json"
        if target_diagnostics.read_bytes() != staged_diagnostics.read_bytes():
            pending = target_diagnostics.with_suffix(".json.live-pending")
            pending.write_bytes(staged_diagnostics.read_bytes())
            pending.replace(target_diagnostics)
        source_att = site / "data/live-fork-attestation.json"
        if not source_att.exists() or source_att.read_bytes() != Path(attestation).read_bytes():
            temporary_att = source_att.with_suffix(".json.live-pending")
            temporary_att.write_bytes(Path(attestation).read_bytes())
            temporary_att.replace(source_att)
        if target.read_bytes() != staged_file.read_bytes():
            temporary = target.with_suffix(".json.live-pending")
            temporary.write_bytes(staged_file.read_bytes())
            temporary.replace(target)
            print("LIVE_PROGRESS_UPDATED", fork_run["sample_count"],
                  public["real_progress"]["candidates"]["ivanka"]["finished"],
                  flush=True)
        else:
            print("LIVE_PROGRESS_UNCHANGED", fork_run["sample_count"],
                  public["real_progress"]["candidates"]["ivanka"]["finished"],
                  flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=SITE)
    for name in ("fork", "fork-runner", "attestation", "fork-repo", "base"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--real", type=Path)
    parser.add_argument("--real-data", type=Path)
    args = parser.parse_args()
    update(args.site, args.fork, args.fork_runner, args.attestation,
           args.fork_repo, args.base, real=args.real, real_data=args.real_data)


if __name__ == "__main__":
    main()
