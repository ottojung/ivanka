"""Publish monotonically growing, source-verified partial benchmark snapshots."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile

from .fork_progress import preview as fork_preview
from .hxb2_preview import preview as old_preview
from .public_dominance import enrich
from .site_build import SITE, validate_public_site

LEGACY_ID = "hxb2-v4-original-run-live"
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


def update(site, old, old_source, fork, fork_runner, attestation, fork_repo, base):
    site = Path(site)
    target = site / "data/runs.json"
    public = json.loads(target.read_text())
    old_run = old_preview(old, old_source)
    old_run.update(id=LEGACY_ID,
                   title="HXB2 v4 · original seven-way MiCall (live, historical)")
    old_run["status_reason"] = (
        f"{old_run['sample_count']}/400 verified original MiCall cases; "
        "historical images lack source-attested fork provenance; NOT qualified.")
    public["runs"] = replace_run(public["runs"], old_run)
    fork_run = fork_preview(fork, fork_runner, attestation, fork_repo, base)
    public["runs"] = replace_run(public["runs"], fork_run)
    public = enrich(public)
    with tempfile.TemporaryDirectory(prefix="bench-live-") as folder:
        staged = Path(folder) / "site"
        shutil.copytree(site, staged)
        shutil.copy2(attestation, staged / "data/live-fork-attestation.json")
        (staged / "data/runs.json").write_text(
            json.dumps(public, sort_keys=True, indent=2) + "\n")
        validate_public_site(staged)
        staged_file = staged / "data/runs.json"
        source_att = site / "data/live-fork-attestation.json"
        if not source_att.exists() or source_att.read_bytes() != Path(attestation).read_bytes():
            temporary_att = source_att.with_suffix(".json.live-pending")
            temporary_att.write_bytes(Path(attestation).read_bytes())
            temporary_att.replace(source_att)
        if target.read_bytes() != staged_file.read_bytes():
            temporary = target.with_suffix(".json.live-pending")
            temporary.write_bytes(staged_file.read_bytes())
            temporary.replace(target)
            print("LIVE_PROGRESS_UPDATED", old_run["sample_count"],
                  fork_run["sample_count"], flush=True)
        else:
            print("LIVE_PROGRESS_UNCHANGED", old_run["sample_count"],
                  fork_run["sample_count"], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=SITE)
    for name in ("old", "old-source", "fork", "fork-runner",
                 "attestation", "fork-repo", "base"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    update(args.site, args.old, args.old_source, args.fork,
           args.fork_runner, args.attestation, args.fork_repo, args.base)


if __name__ == "__main__":
    main()
