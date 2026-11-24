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
from pathlib import Path

from . import exploratory_policy, job_temp, px_metrics, px_retention
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
    # Dispatch in canonical source-ID order, never the arbitrary TSV row order.
    for sample in sorted(ids):
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
    # Synthetic order follows canonical source-ID aliases as well.
    for case_id in sorted(ids):
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
    cleanup = state.get("pilot_cleanup")
    if (isinstance(cleanup, dict) and "pilot_cleanup_error" not in state
            and sched.SHA256.fullmatch(cleanup.get("pilot_container_id") or "")):
        report["retention_container_id"] = cleanup["pilot_container_id"]
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


def extract_diagnostics(root, arm, output_dir, *, fastq_sha256,
                        exact_report=None):
    """Measure final-MAX diagnostics before any scratch can be reclaimed."""
    return px_metrics.record(root, arm, output_dir,
                             fastq_sha256=fastq_sha256,
                             exact_report=exact_report)


def _exact_report(output_dir, case, receipt):
    """Generate an exact-coverage report or fail closed with the reason."""
    from . import exact_cache, px_metrics

    report_path = Path(output_dir) / "exact_coverage.json"
    if report_path.is_file():
        return json.loads(report_path.read_bytes())
    artifact = px_metrics.final_max(output_dir)
    if artifact is None:
        return {"status": "unavailable",
                "unavailable_reason": "no final MAX consensus sequence"}
    try:
        from benchmarks.produce_exact_coverage import generate
    except ImportError as exc:
        return {"status": "unavailable",
                "unavailable_reason": f"exact coverage module unavailable: {exc}"}
    csv_path = Path(output_dir) / "exact_coverage.csv"
    temp = Path(output_dir) / ".exact_coverage.csv.partial"
    try:
        report = generate(case.r1, case.r2, artifact, temp, overlap_size=70)
    except ImportError as exc:
        temp.unlink(missing_ok=True)
        return {"status": "unavailable",
                "unavailable_reason": f"exact coverage module unavailable: {exc}"}
    try:
        temp.replace(csv_path)
        report.update({
            "method": px_metrics.METHOD,
            "source_conseq_sha256": receipt["output_sha256"],
            "source_image_sha256": arm_image(receipt),
            "source_fastq_sha256": [case.input_hashes()["R1"],
                                    case.input_hashes()["R2"]],
            "micall_exact_coverage_module_sha256": exact_cache.SOURCE_SHA256,
            "exact_coverage_sha256": sched.sha256_file(csv_path),
            "exact_coverage_csv": str(csv_path),
        })
        report_path.write_text(json.dumps(report, sort_keys=True) + "\n")
        return report
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def arm_image(receipt):
    value = receipt.get("image_sha256")
    if not isinstance(value, str) or not sched.SHA256.fullmatch(value):
        raise ValueError("receipt missing image sha256")
    return value


def posthoc_extract_and_retain(root, arm, case, receipt, *, scorer=None,
                               scorer_sha=None):
    """Seal posthoc measurements; the supervisor retires with teardown proof."""
    output_dir = Path(root) / "outputs" / (arm["tool_id"] + "-" + arm["alias"])
    if scorer is None:
        from .px_posthoc import build_default_scorer
        scorer = build_default_scorer()
        scorer_sha = scorer.source_sha256
    if scorer_sha is None:
        raise ValueError("posthoc scorer SHA-256 is required")
    result = sched.posthoc_score(root, arm, scorer, scorer_sha,
                                 output_dir=output_dir, case=case)
    path, digest = sched.write_results(root, arm, result)
    Path(str(path) + ".sha256").write_text(digest + "\n")
    exact = _exact_report(output_dir, case, receipt)
    hashes = case.input_hashes()
    px_metrics.record(root, arm, output_dir,
                      fastq_sha256=[hashes["R1"], hashes["R2"]],
                      exact_report=exact)


def reconcile_terminal(root, registry, source, *, scorer=None, scorer_sha=None,
                       aliases=None):
    """Posthoc-reconcile terminal receipts without launching any benchmark.

    Existing successful arms get scoring, diagnostics and resource evidence
    from their retained output. Failed receipts (including infrastructure
    stops like R003) are left untouched except for a resource record carrying
    their observed peak RSS, which may be null.
    """
    sched.build_plan(registry, source, root)  # fails closed on drifted registry
    wanted = set(aliases) if aliases is not None else None
    reconciled, failures = [], []
    for identifier in sched._load_index(root):
        parsed = sched.arm_from_receipt(root, identifier)
        if parsed is None:
            continue
        if wanted is not None and parsed["alias"] not in wanted:
            continue
        receipt = sched.verify_receipt(root, parsed)
        case = source.case(parsed["cohort"], parsed["alias"])
        if case.input_hashes() != parsed["input_sha256"]:
            raise ValueError("terminal receipt input hash differs from source")
        _reconcile_arm(root, parsed, case, receipt, active=None,
                       active_sha=None, scorer=scorer, scorer_sha=scorer_sha,
                       reconciled=reconciled, failures=failures)
    return {"schema": "ivanka.px.reconcile.v1", "reconciled": reconciled,
            "failures_preserved": failures}


def _reconcile_arm(root, parsed, case, receipt, *, active, active_sha,
                   scorer, scorer_sha, reconciled, failures):
    from .px_posthoc import build_default_scorer

    sched.write_resource(root, parsed, receipt)
    if receipt["outcome"] != "success":
        failures.append({"alias": parsed["alias"], "cohort": parsed["cohort"],
                         "reason": receipt["failure_reason"]})
        return
    output = Path(root) / "outputs" / (
        parsed["tool_id"] + "-" + parsed["alias"])
    if active is None:
        active = scorer or build_default_scorer()
        active_sha = scorer_sha or active.source_sha256
    result = sched.posthoc_score(root, parsed, active, active_sha,
                                 output_dir=output, case=case)
    path, digest = sched.write_results(root, parsed, result)
    Path(str(path) + ".sha256").write_text(digest + "\n")
    hashes = case.input_hashes()
    px_metrics.record(root, parsed, output,
                      fastq_sha256=[hashes["R1"], hashes["R2"]],
                      exact_report=_exact_report(output, case, receipt))
    reconciled.append({"alias": parsed["alias"], "cohort": parsed["cohort"],
                       "result_sha256": digest})


def retention_plan(root, arms, budget_bytes=px_retention.BUDGET_BYTES,
                   allocated=None):
    """Bound evidence retention by the 20 GiB policy without deleting anything."""
    return px_retention.plan(root, arms, budget_bytes, allocated)


def apply_retention(root, decision):
    """Reclaim only verified scratch from an in-budget retention plan."""
    return px_retention.apply(root, decision)


def cleanup_disposable(root, scratch, arm, result_path=None):
    """Remove disposable artifacts only after full diagnostics verification."""
    receipt = sched.verify_receipt(root, arm)
    if receipt is None:
        raise ValueError("scratch cleanup requires a verified terminal receipt")
    if result_path is not None:
        sidecar = Path(str(result_path) + ".sha256")
        if (not sidecar.is_file()
                or sidecar.read_text().strip() != sched.sha256_file(result_path)):
            raise ValueError("result hash not yet attested before cleanup")
    target = Path(scratch)
    return px_retention.reclaim_one(root, arm, target=target)


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


def checked_baseline(root, registry):
    """Require the actual immutable PX disk baseline before any worker arms."""
    target = Path(root).resolve() / "budget-baseline.json"
    if not target.is_file():
        return None
    if sched.sha256_file(target) != registry.get("storage_baseline_sha256"):
        return None
    data = json.loads(target.read_bytes())
    if (data.get("schema") != "ivanka.exploratory.storage-baseline.v1"
            or data.get("root") != str(Path(root).resolve())
            or data.get("image_store") != registry["policy"]["dedicated_image_store_root"]
            or data.get("workspace") != "/workspace"
            or data.get("active_job") is not None
            or data.get("frozen_manifest_sha256")
            != registry["policy"]["frozen_seven_manifest_sha256"]):
        return None
    return target


def main():
    """Inert CLI: only plan runs; supervise needs an explicit signed handoff."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--supervise", action="store_true")
    parser.add_argument("--reconcile", action="store_true",
                        help="posthoc-reconcile terminal receipts without launching")
    parser.add_argument("--alias", action="append", dest="aliases",
                        help="limit reconciliation to these public aliases")
    parser.add_argument("--armed", action="store_true")
    parser.add_argument("--check-ready", action="store_true",
                        help="exit 0 only when certified tools and handoffs exist")
    parser.add_argument("--audit-temp", action="store_true",
                        help="audit stale job temporaries at cohort end; no deletion")
    parser.add_argument("--apply-temp", action="store_true",
                        help="reclaim verified stale job temporaries (requires --armed)")
    args = parser.parse_args()
    if args.audit_temp:
        if args.apply_temp and not args.armed:
            parser.error("--apply-temp requires --armed after the single-worker boundary")
        print(json.dumps(job_temp.audit_terminal_temp(args.root,
                                                      apply=args.apply_temp),
                         sort_keys=True))
        return 0
    if args.check_ready:
        data = exploratory_policy.checked(args.registry)
        if checked_baseline(args.root, data) is None:
            return 1
        tools = [name for name in exploratory_policy.EXPERIMENTAL
                 if exploratory_policy.eligible(data, name)]
        if not tools or not all(sup.verify_handoff(args.root, args.registry, name)
                                for name in tools):
            return 1
        print(json.dumps({"ready": tools}, sort_keys=True))
        return 0
    modes = sum(bool(item) for item in (args.plan, args.supervise, args.reconcile))
    if modes != 1:
        parser.error("choose exactly one of --plan, --supervise or --reconcile")
    if args.supervise and not args.armed:
        parser.error("supervise requires --armed after image-agent handoff")
    source = load_cohort()
    if args.reconcile:
        result = reconcile_terminal(args.root, args.registry, source,
                                    aliases=args.aliases)
        print(json.dumps(result, sort_keys=True))
        return
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
    baseline = checked_baseline(args.root, exploratory_policy.checked(args.registry))
    if baseline is None:
        raise ValueError("missing or changed PX storage baseline")
    runner = SupervisedRunner(args.registry, baseline, launch.operate, args.root)
    result = sup.BackgroundSupervisor(args.registry, baseline, source, args.root,
                                      runner,
                                      diagnostics=posthoc_extract_and_retain
                                      ).start(armed=True)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
