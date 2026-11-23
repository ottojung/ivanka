"""Inert executable integration for the NONQUALIFYING PX cohort.

Nothing here starts a worker on import. ``run_guarded`` delegates each single
case to the merged PR411 launcher under its exclusive lock. The supervisor
wires these helpers together only after image-agent handoff releases the PX
worker; no live process is started by importing or testing this module.
"""
import argparse
import csv
import json
import secrets
import shutil
from pathlib import Path

from . import exploratory_policy
from . import px_cohort_scheduler as sched
from . import px_supervisor as sup
from .exploratory_runtime import launch

PHYSICAL_ROOT = Path("/workspace/denovo-example-io-1")
PHYSICAL_MANIFEST = PHYSICAL_ROOT / "manifest.tsv"
SYNTHETIC_ROOT = Path("/workspace/ivanka-synthetic-abundance15-464-20261117")
TIMER = Path(__file__).resolve().parents[2] / "benchmarks/inside_container_timing.py"
RESERVE_BYTES = 1024**3
# Only read-pair mounts and the in-container timer enter an assembler.
REFERENCE_TOKENS = ("truth", "hidden", "hxb2", "reference", "subtype", "panel")


def load_physical(root=PHYSICAL_ROOT, expected_sha=None):
    """Derive R001..R198 from the original manifest's sorted sample names."""
    manifest = Path(root) / "manifest.tsv"
    expected = expected_sha or sched.PHYSICAL_MANIFEST_SHA256
    if sched.sha256_file(manifest) != expected:
        raise ValueError("original physical manifest SHA256 changed")
    with manifest.open(newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    ids = [row["sample"] for row in rows]
    if len(ids) != sched.PHYSICAL_COUNT or len(set(ids)) != len(ids):
        raise ValueError("physical manifest is not the frozen 198-case cohort")
    aliases = sched.canonical_aliases(ids, "physical")
    cases = []
    for sample in ids:
        folder = Path(root) / "samples" / sample
        r1 = folder / (sample + "_L001_R1_001.fastq.gz")
        r2 = folder / (sample + "_L001_R2_001.fastq.gz")
        if not r1.is_file() or not r2.is_file():
            raise ValueError("original physical read pair is missing: " + sample)
        cases.append(sched.CasePair(sample, aliases[sample], "physical", r1, r2))
    return cases


def load_synthetic(root=SYNTHETIC_ROOT, cohort=None, expected_sha=None):
    """Derive H001..H464 from sorted v6 case IDs; never read hidden truth."""
    source = Path(cohort or sched.SYNTHETIC_COHORT)
    if sched.sha256_file(source) != (expected_sha or sched.SYNTHETIC_COHORT_SHA256):
        raise ValueError("original v6 cohort SHA256 changed")
    records = json.loads(source.read_bytes())["cases"]
    ids = [item["id"] for item in records]
    if len(ids) != sched.SYNTHETIC_COUNT or len(set(ids)) != len(ids):
        raise ValueError("v6 cohort is not the frozen 464-case cohort")
    aliases = sched.canonical_aliases(ids, "synthetic")
    cases = []
    for case_id in ids:
        reads = Path(root) / case_id / "reads"
        r1, r2 = reads / "R1.fastq.gz", reads / "R2.fastq.gz"
        if not r1.is_file() or not r2.is_file():
            raise ValueError("original synthetic read pair is missing: " + case_id)
        cases.append(sched.CasePair(case_id, aliases[case_id], "synthetic", r1, r2))
    return cases


def load_cohort(root=PHYSICAL_ROOT, synthetic_root=SYNTHETIC_ROOT):
    """One source covering 198 physical then 464 synthetic read-only pairs."""
    return sched.CohortSource(
        load_physical(root),
        load_synthetic(synthetic_root),
        physical_manifest=Path(root) / "manifest.tsv",
        synthetic_cohort=sched.SYNTHETIC_COHORT,
    )


def _reads_mount(case):
    reads = Path(case.r1).resolve().parent
    if reads != Path(case.r2).resolve().parent:
        raise ValueError("paired reads must share one read-only mount")
    return reads


def micall_argv(tool, image, case, output_dir, *, timeout=2400):
    """Build the exact foreground Podman+MiCall argv for one case."""
    if tool not in exploratory_policy.EXPERIMENTAL:
        raise ValueError("unregistered PX explorer cannot be executed")
    if not sched.SHA256.fullmatch(image or ""):
        raise ValueError("PX run requires a source-bound image digest")
    argv = [
        "podman", "run", "--rm", "--pull=never", "--userns=host", "--cpus=2",
        "--name", "px-" + tool + "-" + secrets.token_hex(8),
        "--timeout", str(timeout),
        "-v", f"{_reads_mount(case)}:/reads:ro",
        "-v", f"{Path(output_dir).resolve()}:/results:rw",
        "-v", f"{TIMER}:/ivanka-timer.py:ro",
        "--entrypoint", "/opt/venv/bin/python", image,
        "/ivanka-timer.py", "/results/timing.json",
        "micall", "analyze", "sample",
        "/reads/" + Path(case.r1).name, "/reads/" + Path(case.r2).name,
        "/results", "--denovo", "--keep_scratch", "--all_projects",
    ]
    assert_reference_blind(argv)
    return argv


def assert_reference_blind(argv):
    """Fail closed if truth/reference leaves the independent scorer."""
    for token in argv:
        if any(word in str(token).lower() for word in REFERENCE_TOKENS):
            raise ValueError("reference or truth path in assembler argv")


def final_max(output_dir):
    """Locate MiCall's frozen final MAX artifact, never a raw contig."""
    root = Path(output_dir)
    for candidate in (root / sched.MAX_ARTIFACT,
                      root / "scratch" / sched.MAX_ARTIFACT):
        if candidate.is_file():
            return candidate
    return None


def classify(state):
    """Map launcher terminal states into bounded receipt failure reasons."""
    if state.get("status") == "finished":
        return "success"
    reason = state.get("reason")
    if reason == "disk_limit":
        return "disk_stop"
    if reason in sched.FAILURE_REASONS:
        return reason
    return "error"


def run_guarded(registry, baseline, arm, case, output_dir, operate,
                reserve_bytes=RESERVE_BYTES):
    """Delegate ONE case to the locked launcher; never loop over a cohort."""
    report = {"alias": arm["alias"], "cohort": arm["cohort"],
              "input_sha256": arm["input_sha256"]}
    argv = micall_argv(arm["tool_id"], arm["image_sha256"], case,
                       output_dir)
    state = operate(registry, baseline, arm["tool_id"], "pilot", argv,
                    reserve_bytes)
    outcome = classify(state)
    report["runner_receipt_sha256"] = state.get("log_sha256")
    report["peak_rss"] = state.get("peak_rss")
    if outcome != "success":
        report.update(outcome="failure", failure_reason=outcome)
        return report
    artifact = final_max(output_dir)
    if artifact is None:
        report.update(outcome="failure", failure_reason="no_final_max")
        return report
    timing = Path(output_dir) / "timing.json"
    seconds = None
    if timing.is_file():
        clock = json.loads(timing.read_bytes())
        if clock.get("exit_code") == 0 and clock.get("seconds", 0) > 0:
            seconds = clock["seconds"]
    if not isinstance(seconds, (int, float)) or seconds <= 0:
        report.update(outcome="failure", failure_reason="error")
        return report
    report.update(outcome="success", output_path=artifact, seconds=seconds)
    return report


def posthoc(root, arm, scorer, scorer_sha):
    """Score a terminal successful arm with a source-frozen external scorer."""
    result = sched.posthoc_score(root, arm, scorer, scorer_sha)
    path, digest = sched.write_results(root, arm, result)
    Path(str(path) + ".sha256").write_text(digest + "\n")
    return path, digest


def cleanup_disposable(root, scratch, arm, result_path):
    """Remove scratch only after receipt and result content hashes verify."""
    target = Path(scratch).resolve()
    base = Path(root).resolve()
    if not target.is_relative_to(base) or target == base:
        raise ValueError("scratch cleanup escaped the PX root")
    if target.name not in ("scratch", "tmp"):
        raise ValueError("only disposable scratch may be removed")
    if sched.verify_receipt(root, arm) is None:
        raise ValueError("scratch cleanup requires a verified terminal receipt")
    sidecar = Path(str(result_path) + ".sha256")
    if (not sidecar.is_file()
            or sidecar.read_text().strip() != sched.sha256_file(result_path)):
        raise ValueError("result hash not yet attested before cleanup")
    shutil.rmtree(target)
    return {"removed": str(target), "reason": "hashes_verified"}


class SupervisedRunner:
    """Runner adapter for ``px_supervisor.BackgroundSupervisor``."""

    def __init__(self, registry, baseline, operate, root,
                 reserve_bytes=RESERVE_BYTES):
        self.registry, self.baseline, self.operate = registry, baseline, operate
        self.root, self.reserve_bytes = Path(root), reserve_bytes

    def __call__(self, arm, case):
        output = self.root / "outputs" / (arm["tool_id"] + "-" + arm["alias"])
        output.mkdir(parents=True, exist_ok=True)
        return run_guarded(self.registry, self.baseline, arm, case, output,
                           self.operate, self.reserve_bytes)


def main():
    """Inert CLI: only plan runs; supervise needs an explicit signed handoff."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--supervise", action="store_true")
    parser.add_argument("--armed", action="store_true")
    args = parser.parse_args()
    if args.plan == args.supervise:
        parser.error("choose exactly one of --plan or --supervise")
    if args.supervise and not args.armed:
        parser.error("supervise requires --armed after image-agent handoff")
    source = load_cohort()
    plan = sched.build_plan(args.registry, source, args.root)
    if args.plan:
        print(json.dumps({"tools": plan["tools"], "total": plan["total_arms"],
                          "pending": plan["pending_arms"]}, sort_keys=True))
        return
    if not plan["tools"]:
        parser.error("no source-bound image/pilot proof for any explorer")
    for tool in plan["tools"]:
        if not sup.verify_handoff(args.root, args.registry, tool):
            raise sup.HandoffRequired("missing verified handoff for " + tool)
    baseline = args.root / "baseline.json"
    runner = SupervisedRunner(args.registry, baseline, launch.operate, args.root)
    result = sup.BackgroundSupervisor(args.registry, baseline, source,
                                      args.root, runner).start(armed=True)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
