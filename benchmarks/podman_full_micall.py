#!/usr/bin/env python3
"""Real end-to-end comparison using two containers of the same MiCall build.

Runs MiCall's public CLI; no direct Python monkeypatch or recreated mapping.
All clinical input and results must remain outside this public repository.
"""
import argparse
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math
import os
import shutil
from pathlib import Path
import subprocess
import time

from Bio import SeqIO
from Bio.Align import PairwiseAligner
from reference_catalog import load_micall_projects
import milestone198
from container_completion import (TIMING_ORIGIN, verified_internal_seconds,
                                  authenticated_postrun_cleanup, startup_database_lock,
                                  no_micall_output)

DATA = Path(os.environ.get("IVANKA_DATA", "/workspace/denovo-example-io-1"))
RESULTS = Path(os.environ.get("IVANKA_PODMAN_RESULTS", "/workspace/ivanka-podman-results"))
IVA_BASELINE_CACHE = Path(os.environ.get("IVANKA_IVA_BASELINE_CACHE", "/workspace/ivanka-iva-baseline-cache"))
IVA_IMAGE = os.environ.get("IVANKA_IVA_IMAGE", "localhost/ivanka-micall-iva:base")
IVANKA_IMAGE = os.environ.get("IVANKA_IVANKA_IMAGE", "localhost/ivanka-micall-ivanka:seeded")
OUTPUT_NAMES = ("conseq.csv", "conseq_all.csv", "contigs.csv", "unstitched_contigs.csv",
                "stitched_contigs.csv", "genome_coverage.csv", "genome_concordance.csv",
                "remap_counts.csv", "coverage_summary.csv", "concordance.csv",
                "nuc.csv", "amino.csv", "insertions.csv", "coverage_scores.csv")


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def image_id(ref):
    return subprocess.check_output(["podman", "image", "inspect",
                                    "--format", "{{.Id}}", ref], text=True).strip()


def pinned_run_images(configured, verified, pinned_iva_id):
    """Run by immutable image IDs, never by mutable tags after preflight."""
    return {
        arm: verified.get(arm, pinned_iva_id if arm == "iva" else ref)
        for arm, ref in configured.items()
    }


def recorded_image_id(ref):
    """Reuse an immutable preflight-pinned Podman ID without another inspect.

    The benchmark pins image references to verified IDs before starting any
    sample. Mutable tags still require an actual Podman inspection.
    """
    if len(ref) == 64 and all(char in "0123456789abcdef" for char in ref):
        return ref
    return image_id(ref)


def image_layers(ref):
    raw = subprocess.check_output(
        ["podman", "image", "inspect", "--format", "{{json .RootFS.Layers}}", ref],
        text=True).strip()
    return json.loads(raw)


def verify_identical_micall_base(iva_image, ivanka_image):
    """Compare immutable container layer digests, not mutable image tags."""
    baseline = image_layers(iva_image)
    experiment = image_layers(ivanka_image)
    if not baseline or experiment[:len(baseline)] != baseline:
        raise ValueError("Ivanka image does not derive from the selected IVA MiCall base image")


def verify_ivanka_image_binding(image):
    """One container startup verifies AST binding, cache key, both reads and binary."""
    verifier = Path(__file__).with_name("verify_ivanka_binding.py").read_text()
    try:
        subprocess.run(["podman", "run", "--rm", "--pull=never", "--entrypoint",
                        "python", image, "-c", verifier],
                       check=True, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Timed out waiting for Ivanka image binding verification") from exc
    except (subprocess.CalledProcessError, OSError) as exc:
        raise ValueError("Ivanka image failed executable-binding verification") from exc


def score_outputs(folder, reference):
    """Inspect the final MiCall products without materializing whole CSVs in RAM."""
    aligner = PairwiseAligner()
    aligner.mode = "global"
    aligner.end_gap_score = -1
    scores = []
    lengths = []
    result = {}
    depth = {"positions":0,"covered_positions":0,"positions_ge_10":0,
             "positions_ge_100":0,"sum_depth":0.0,"maximum_depth":0.0}
    unique_covered=set()
    unique_ge_10=set()
    unique_ge_100=set()
    for basename in OUTPUT_NAMES:
        matches = [path for path in (folder / basename, folder / "scratch" / basename)
                   if path.is_file()]
        if not matches:
            result[basename] = {"exists": False}
            continue
        file = matches[0]  # Final collated MiCall output has priority.
        rowcount=0
        with file.open(newline="") as f:
            reader=csv.DictReader(f)
            for row in reader:
                rowcount+=1
                if basename == "conseq.csv":
                    if row.get("consensus-percent-cutoff") != "MAX":
                        continue
                    seq = row.get("sequence","").upper()
                    if seq:
                        lengths.append(len(seq))
                        if reference is not None:
                            scores.append(float(aligner.score(reference,seq)))
                elif basename == "genome_coverage.csv":
                    value = row.get("coverage")
                    if value in (None,""):
                        continue
                    try:
                        coverage=float(value)
                    except ValueError:
                        continue
                    depth["positions"]+=1
                    depth["sum_depth"]+=coverage
                    depth["maximum_depth"]=max(depth["maximum_depth"],coverage)
                    if coverage > 0: depth["covered_positions"]+=1
                    if coverage >= 10: depth["positions_ge_10"]+=1
                    if coverage >= 100: depth["positions_ge_100"]+=1
                    # Rows are not unique genome coordinates: multiple
                    # contigs may cover the same HXB2 position. Report both.
                    ref=row.get("coordinates")
                    pos=row.get("refseq_nuc_pos")
                    if ref and pos:
                        coordinate=(ref,pos)
                        if coverage > 0: unique_covered.add(coordinate)
                        if coverage >= 10: unique_ge_10.add(coordinate)
                        if coverage >= 100: unique_ge_100.add(coordinate)
        result[basename]={"exists":True,"rows":rowcount,"sha256":sha(file)}
    return {"best_hxb2_final_max_conseq_score": max(scores,default=None),
            "num_final_max_conseqs":len(lengths),
            "final_max_conseq_lengths":sorted(lengths,reverse=True),
            "coverage_depth": {
                "positions":depth["positions"],
                "covered_positions":depth["covered_positions"],
                "positions_ge_10":depth["positions_ge_10"],
                "positions_ge_100":depth["positions_ge_100"],
                "mean_depth":(depth["sum_depth"]/depth["positions"]
                              if depth["positions"] else None),
                "maximum_depth":depth["maximum_depth"],
                "unique_reference_positions_covered":len(unique_covered),
                "unique_reference_positions_ge_10":len(unique_ge_10),
                "unique_reference_positions_ge_100":len(unique_ge_100),
            },
            "outputs":result}

def compare_outputs(iva, ivanka):
    """Report downstream MiCall differences without assuming only one contig."""
    left, right = iva["outputs"], ivanka["outputs"]
    results = {}
    for filename in sorted(set(left) | set(right)):
        a = left.get(filename, {})
        b = right.get(filename, {})
        results[filename] = {
            "both_present": a.get("exists", False) and b.get("exists", False),
            "same_sha256": (a.get("sha256") == b.get("sha256")
                            if a.get("sha256") and b.get("sha256") else None),
            "iva_rows": a.get("rows"),
            "ivanka_rows": b.get("rows"),
            "row_delta": (b["rows"] - a["rows"]
                          if "rows" in a and "rows" in b else None),
        }
    return results


def best_consensus_acceptance(iva_score, ivanka_score):
    """A single good final MiCall MAX consensus is sufficient.

    Non-positive baselines use absolute comparison rather than a relative
    threshold, which would be meaningless for negative alignment scores.
    """
    threshold = (0.95*iva_score if iva_score > 0 else iva_score) if iva_score is not None else None
    return {
        "iva_score": iva_score,
        "ivanka_score": ivanka_score,
        "threshold": threshold,
        "pass": threshold is not None and ivanka_score is not None and ivanka_score >= threshold,
    }


QUALIFICATION_MAX_SECONDS = 1800
QUALIFY_SAMPLE_COUNT = 18
ORIGINAL_COHORT_SIZE = 20
IVA_INELIGIBLE_COUNT = 2


def qualification_within_cap(configured_limit, elapsed):
    """Require each sample to finish within the 30-minute cap.

    A separate IVA-only control preparation is never an alpha qualification.
    """
    return (isinstance(configured_limit, (int,float)) and
            isinstance(elapsed, (int,float)) and
            0 < configured_limit <= QUALIFICATION_MAX_SECONDS and
            0 <= elapsed <= configured_limit)


def verify_iva_eligibility(manifest_sha, eligible_names):
    """Require independently recorded IVA-only exclusions, never Ivanka-based culling.

    The private evidence file records the original frozen cohort and two
    successful, zero-MAX IVA controls independently repeated with and
    without the MiCall all-projects mode.
    """
    path = DATA / "iva_eligibility_evidence.json"
    try:
        info = json.loads(path.read_text())
        excluded = info["excluded"]
        valid = (
            info["source_count"] == ORIGINAL_COHORT_SIZE
            and info["eligible_count"] == QUALIFY_SAMPLE_COUNT
            and info["excluded_count"] == IVA_INELIGIBLE_COUNT
            and info["eligible_manifest_sha256"] == manifest_sha
            and len(excluded) == IVA_INELIGIBLE_COUNT
            and len({entry["sample"] for entry in excluded}) == IVA_INELIGIBLE_COUNT
            and not ({entry["sample"] for entry in excluded} & set(eligible_names))
            and all(
                entry[mode]["iva_exit"] == 0 and entry[mode]["iva_max"] == 0
                for entry in excluded
                for mode in ("all_projects", "without_all_projects")
            )
            and isinstance(info["source_manifest_sha256"], str)
            and len(info["source_manifest_sha256"]) == 64
        )
        if not valid:
            raise ValueError("IVA eligibility evidence is inconsistent with the frozen cohort")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ValueError("Missing or invalid pinned IVA eligibility evidence") from exc
    return {
        "source_manifest_sha256": info["source_manifest_sha256"],
        "iva_ineligible_excluded": IVA_INELIGIBLE_COUNT,
        "iva_eligibility_evidence_sha256": sha(path),
    }


def project_aware_acceptance(iva_dir, ivanka_dir):
    """Score real final MiCall Ivanka consensus against final IVA consensus."""
    def sequences(directory):
        path=next((p for p in (directory/"conseq.csv", directory/"scratch"/"conseq.csv")
                   if p.is_file()),None)
        if path is None:
            raise ValueError("Missing final conseq.csv")
        with path.open(newline="") as handle:
            reader=csv.DictReader(handle)
            return [row["sequence"].upper() for row in reader
                    if row.get("consensus-percent-cutoff")=="MAX" and row.get("sequence")]
    targets=sequences(iva_dir)
    candidates=sequences(ivanka_dir)
    if not targets or not candidates:
        raise ValueError("No final MAX MiCall consensus")
    maxlen=max(map(len,targets))
    aligner=PairwiseAligner()
    aligner.mode="global"
    aligner.match_score=1
    aligner.mismatch_score=-1
    aligner.open_gap_score=-2
    aligner.extend_gap_score=-1
    best=max(aligner.score(ref,seq) for ref in targets
             if len(ref)>=0.95*maxlen for seq in candidates)
    return {"method":"final_iva_max_consensus_global_alignment",
            "iva_score":float(maxlen),"ivanka_score":float(best),
            "threshold":0.95*maxlen,"pass":best>=0.95*maxlen,
            "iva_final_max_count":len(targets),
            "ivanka_final_max_count":len(candidates)}


def baseline_provenance(row, iva_image_id, hxb2_sha256, all_projects=False):
    sample = row["sample"]
    sample_dir = DATA / "samples" / sample
    fastqs = [sample_dir / f"{sample}_L001_R{i}_001.fastq.gz" for i in (1, 2)]
    return {
        "iva_image_id": iva_image_id,
        "hxb2_sha256": hxb2_sha256,
        "all_projects": bool(all_projects),
        "fastq_sha256": [sha(f) for f in fastqs],
        "micall_project_code": row.get("micall_project_code", "").strip(),
    }


def iva_baseline_path(sample):
    """Stable, shared directory independent of any one benchmark invocation."""
    if not sample or Path(sample).name != sample or sample in (".", ".."):
        raise ValueError("Invalid sample name for IVA cache")
    return IVA_BASELINE_CACHE / sample / "baseline.json"


def load_iva_baseline(sample, expected_provenance):
    path = iva_baseline_path(sample)
    if not path.is_file():
        raise ValueError("No verified IVA baseline for this sample; import existing IVA results")
    stored = json.loads(path.read_text())
    if stored["provenance"] != expected_provenance:
        raise ValueError("IVA baseline provenance differs from current MiCall image, FASTQs, or HXB2")
    arm = stored["iva"]
    if arm.get("image_id") != expected_provenance["iva_image_id"]:
        raise ValueError("Cached IVA arm image ID differs from verified control provenance")
    if arm["exit_code"] != 0 or arm["metrics"]["num_final_max_conseqs"] <= 0:
        raise ValueError("The stored IVA baseline is not a completed scored MiCall run")
    output = Path(arm.get("artifact_dir", "")) / "conseq.csv"
    expected = arm["metrics"].get("outputs", {}).get("conseq.csv", {}).get("sha256")
    if not expected or not output.is_file() or sha(output) != expected:
        raise ValueError("Cached IVA final MAX artifact missing or changed")
    return arm


def save_iva_baseline(sample, provenance, arm):
    """Persist independently verified IVA metadata and final MAX sequences.

    A result directory may be removed after the run; the cache must survive.
    Never infer a successful IVA exit from the mere presence of a CSV.
    """
    if arm.get("exit_code") != 0 or arm.get("metrics", {}).get("num_final_max_conseqs", 0) <= 0:
        raise ValueError("Cannot cache an incomplete or unscored IVA baseline")
    if arm.get("image_id") != provenance.get("iva_image_id"):
        raise ValueError("IVA result image ID does not match control provenance")
    folder = Path(arm.get("artifact_dir", ""))
    source = next((p for p in (folder/"conseq.csv", folder/"scratch"/"conseq.csv") if p.is_file()), folder/"conseq.csv")
    expected = arm["metrics"].get("outputs", {}).get("conseq.csv", {}).get("sha256")
    if not expected or not source.is_file() or sha(source) != expected:
        raise ValueError("IVA final MAX artifact missing or checksum mismatched")
    path = iva_baseline_path(sample)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    IVA_BASELINE_CACHE.chmod(0o700)
    path.parent.chmod(0o700)
    target = path.parent / "conseq.csv"
    temporary = path.parent / (".conseq-" + str(os.getpid()) + "-" + str(time.time_ns()))
    shutil.copyfile(source, temporary)
    try:
        if sha(temporary) != expected:
            raise ValueError("IVA artifact changed during cache import")
        temporary.replace(target)
        target.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)
    cached_arm = dict(arm)
    cached_arm["source_artifact_dir"] = str(source.parent)
    cached_arm["artifact_dir"] = str(path.parent.resolve())
    metadata = path.parent / (".baseline-" + str(os.getpid()) + "-" + str(time.time_ns()))
    try:
        metadata.write_text(json.dumps({"provenance": provenance, "iva": cached_arm}, sort_keys=True))
        metadata.chmod(0o600)
        metadata.replace(path)
    finally:
        metadata.unlink(missing_ok=True)
    return cached_arm


def import_iva_baselines(sources, rows, image, hxb2_hash, all_projects):
    """Import completed IVA controls from prior benchmark directories, without running IVA."""
    by_sample = {row["sample"]: row for row in rows}
    imported = 0
    rejected = 0
    memo = {}
    for source in sources:
        root = Path(source)
        if not root.is_dir():
            raise ValueError("IVA import directory does not exist: " + str(root))
        candidates = []
        for file in (root / "iva-baselines").glob("*.json"):
            try:
                value = json.loads(file.read_text())
                candidates.append((file.stem, value.get("provenance"), value.get("iva")))
            except (ValueError, OSError, TypeError):
                rejected += 1
        records = root / "results.jsonl"
        if records.is_file():
            with records.open() as handle:
                for line in handle:
                    try:
                        record = json.loads(line)
                    except ValueError:
                        rejected += 1
                        continue
                    if isinstance(record.get("iva"), dict):
                        candidates.append((record.get("sample"), record.get("provenance"), record["iva"]))
        for name, provenance, arm in candidates:
            row = by_sample.get(name)
            if row is None or not isinstance(arm, dict):
                continue
            if name not in memo:
                memo[name] = baseline_provenance(row, image, hxb2_hash, all_projects)
            expected = memo[name]
            if provenance != expected:
                rejected += 1
                continue
            try:
                load_iva_baseline(name, expected)
                continue
            except (ValueError, OSError, KeyError):
                pass
            try:
                save_iva_baseline(name, expected, arm)
                imported += 1
            except (ValueError, OSError, KeyError):
                rejected += 1
    return {"imported": imported, "rejected": rejected}


def iva_cache_status(rows, image, hxb2_hash, all_projects, require_internal_timing=False):
    status = {"verified": [], "missing_or_invalid": [], "cache_dir": str(IVA_BASELINE_CACHE)}
    for row in rows:
        name = row["sample"]
        expected = baseline_provenance(row, image, hxb2_hash, all_projects)
        try:
            control = load_iva_baseline(name, expected)
            if require_internal_timing and (control.get("timing_origin") != "micall_in_container_monotonic_v1"
                    or not isinstance(control.get("seconds"), (int, float))
                    or isinstance(control.get("seconds"), bool)
                    or not math.isfinite(control["seconds"]) or control["seconds"] <= 0):
                raise ValueError("IVA control requires genuine in-container execution timing")
            status["verified"].append(name)
        except (ValueError, OSError, KeyError):
            status["missing_or_invalid"].append(name)
    return status


def run_arm(row, arm, image, reference, timeout, invocation, all_projects=False):
    name = row["sample"]
    folder = RESULTS / invocation / name / arm
    folder.mkdir(parents=True, exist_ok=True)
    source = DATA / "samples" / name
    fq = [source / f"{name}_L001_R{i}_001.fastq.gz" for i in (1, 2)]
    for file in fq:
        if not file.is_file():
            raise FileNotFoundError(file)
    badcycles = folder / "bad_cycles.csv"
    badcycles.write_text("tile,cycle\n")
    timing_file = folder / "micall_internal_timing.json"
    timing_file.unlink(missing_ok=True)
    timer_script = Path(__file__).resolve().with_name("inside_container_timing.py")
    container_sample = "/bench/samples/" + name
    # The manifest project is a cohort label, NOT MiCall primer project_code.
    project = row.get("micall_project_code", "").strip()
    container_name = f"ivanka-bench-{arm}-{invocation}-{hashlib.sha256(name.encode()).hexdigest()[:8]}"
    command = [
        "podman", "run", "--rm", "--pull=never", "--name", container_name,
        # Podman enforces a container lifetime even when the supervising
        # Python process receives SIGKILL.
        "--timeout", str(max(1,int(timeout)-2)), "--stop-timeout", "2",
        "-v", f"{DATA.resolve()}:/bench:ro",
        "-v", f"{RESULTS.resolve()}:/results:rw",
        "-v", f"{timer_script}:/ivanka-timer.py:ro",
        # Both Podman and its host-side supervisor enforce whole-container
        # deadlines, including startup; there is no separate MiCall deadline.
        "--label", f"org.ottojung.ivanka.benchmark.invocation={invocation}",
        "--entrypoint", "python", image,
        "/ivanka-timer.py",
        f"/results/{invocation}/{name}/{arm}/micall_internal_timing.json",
        "micall", "analyze", "sample",
        f"{container_sample}/{fq[0].name}",
        f"{container_sample}/{fq[1].name}",
        f"/results/{invocation}/{name}/{arm}",
        "--denovo", "--keep_scratch",
        "--bad_cycles_csv", f"/results/{invocation}/{name}/{arm}/bad_cycles.csv",
    ]
    if project:
        command.extend(["--project_code", project])
    if all_projects:
        command.append("--all_projects")
    start = time.monotonic()
    cleanup_error = None
    with (folder / "podman.stdout.log").open("w") as stdout, \
         (folder / "podman.stderr.log").open("w") as stderr:
        start_retries = 0
        original_name = container_name
        while True:
            # The original sample wall clock includes *every* failed startup,
            # backoff, and successful container. Never reset its deadline.
            remaining = timeout - (time.monotonic() - start)
            if remaining <= 1:
                exitcode = 124
                break
            container_name = (original_name if start_retries == 0
                              else f"{original_name}-dbretry{start_retries}")
            command[command.index("--name") + 1] = container_name
            command[command.index("--timeout") + 1] = str(max(1, int(remaining) - 2))
            try:
                p = subprocess.run(command, stdout=stdout, stderr=stderr,
                                   timeout=remaining, check=False)
                exitcode = p.returncode
            except subprocess.TimeoutExpired:
                # The container may outlive its Podman CLI. Cleanup failure
                # cannot hide a real deadline violation.
                exitcode = 124
                try:
                    cleanup = subprocess.run(
                        ["podman", "rm", "--force", container_name],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        timeout=30, check=False)
                    if cleanup.returncode:
                        cleanup_error = f"podman rm exited {cleanup.returncode}"
                except (subprocess.TimeoutExpired, OSError) as exc:
                    cleanup_error = f"{type(exc).__name__}: {exc}"
            stderr.flush()
            # Podman 5.8 sometimes cannot begin its SQLite creation
            # transaction amid concurrent container cleanup. Such a failure
            # has executed ZERO MiCall steps; retry within the ORIGINAL cap,
            # never for non-lock failures or a container that has run MiCall.
            if (exitcode in (125, 126)
                    and startup_database_lock(folder / "podman.stderr.log")
                    and no_micall_output(folder)
                    and not timing_file.exists()
                    and time.monotonic() - start + 3 < timeout):
                start_retries += 1
                stderr.write(f"Benchmark: retrying Podman startup after DB lock ({start_retries})\n")
                stderr.flush()
                time.sleep(min(3 + start_retries, 10))
                continue
            break
    container_wall_seconds = round(time.monotonic()-start, 2)
    internal_seconds = None
    timing_error = None
    recovered_cleanup = False
    if exitcode == 0:
        try:
            internal_seconds = verified_internal_seconds(timing_file, container_wall_seconds)
        except (OSError, KeyError, ValueError, TypeError) as exc:
            exitcode = 1
            timing_error = f"Missing or invalid in-container timing evidence: {exc}"
    elif exitcode == 127:
        # Podman can report 127 when auto-removal fails on a locked DB AFTER
        # MiCall has exited successfully. This case has to satisfy an exact
        # post-run diagnostic and the independent in-container timer.
        internal_seconds = authenticated_postrun_cleanup(
            exitcode, folder, container_wall_seconds)
        if internal_seconds is not None:
            recovered_cleanup = True
            exitcode = 0
    result = {
        "exit_code": exitcode,
        "container_wall_seconds": container_wall_seconds,
        "image_id": recorded_image_id(image), "image": image,
        "artifact_dir": str(folder.resolve()),
        "metrics": score_outputs(folder, reference),
    }
    if start_retries:
        result["podman_start_retries"] = start_retries
    if recovered_cleanup:
        # Preserve the real CLI error; never disguise it as a clean Podman exit.
        result["podman_exit_code"] = 127
        result["postrun_cleanup_error"] = "Podman auto-removal: database is locked"
    if internal_seconds is not None and not timing_error:
        result["seconds"] = internal_seconds
        result["timing_origin"] = TIMING_ORIGIN
    if exitcode:
        result["error"] = (timing_error or
                           (f"Podman arm timed out after {timeout}s" if exitcode == 124
                            else (folder / "podman.stderr.log").read_text()[-1200:]))
    if cleanup_error:
        result["cleanup_error"] = cleanup_error
    return result


def alignment_score_floor(args):
    """Diagnostic 90% is opt-in; alpha keeps 95%, formal 198 always uses 90%."""
    return (milestone198.SCORE_FLOOR
            if getattr(args, "qualify_198", False)
            or getattr(args, "diagnostic_90_floor", False) else 0.95)


def evaluate_sample(row, args, images, checked, pinned_iva_id,
                    hxb2_hash, reference, project_catalog, invocation, deadline=None,
                    reference_panel=None):
    """Run one sample through selected real MiCall image(s), with no shared scratch."""
    name = row["sample"]
    record={"sample":name,"invocation":invocation,
            "hxb2_sha256":hxb2_hash,"status":"started"}
    started=time.monotonic()
    deadline=started+getattr(args,"sample_time_limit",1800)
    failures=0
    try:
        if deadline-time.monotonic() <= 1:
            record["status"]="sample_timeout"
            record["error"]="No per-sample time budget before starting sample"
            record["failed"]=True
            return record
        provenance=baseline_provenance(row,pinned_iva_id,hxb2_hash,getattr(args,"all_projects",False))
        record["provenance"]=provenance
        reused_baseline=None
        if args.mode=="ivanka":
            try:
                reused_baseline=load_iva_baseline(name,provenance)
                record["iva_baseline_reused"]=True
                record["iva"]=reused_baseline
            except (ValueError,OSError,KeyError) as exc:
                if not args.allow_missing_baseline:
                    raise
                # Useful to measure real Ivanka-MiCall runtime/output while
                # preparing costly IVA controls. Never mark it as accepted.
                record["baseline_error"]=str(exc)
        arms=[arm for arm in ("iva","ivanka") if arm in checked]
        def attempt(arm):
            remaining=deadline-time.monotonic()
            if remaining <= 1:
                return arm,{"exit_code":124,
                            "error":"Per-sample time limit exhausted before arm"}
            try:
                result=run_arm(row,arm,images[arm],
                               str(reference) if row.get("project")=="NFLHIVDNA" else None,
                               min(args.timeout_per_arm,max(1,int(remaining))),
                               invocation, getattr(args,"all_projects",False))
            except Exception as exc:
                result={"exit_code":1,"error":f"{type(exc).__name__}: {exc}"}
            return arm,result

        for arm in arms:
            print(f"{name}: {arm}",flush=True)
        if args.parallel_arms and len(arms)==2:
            with ThreadPoolExecutor(max_workers=2) as arm_executor:
                arm_jobs=[arm_executor.submit(attempt,arm) for arm in arms]
                results=[task.result() for task in as_completed(arm_jobs)]
        else:
            results=[attempt(arm) for arm in arms]
        for arm,result in results:
            record[arm]=result
            if result.get("exit_code"):
                failures+=1
                if result["exit_code"]==124:
                    record["status"]="sample_timeout"
        if "iva" in checked and "iva" in record and "metrics" in record["iva"]:
            try:
                save_iva_baseline(name,provenance,record["iva"])
            except ValueError as exc:
                record["baseline_error"]=str(exc)
                failures+=1
        baseline=record.get("iva",reused_baseline)
        if "ivanka" in checked:
            if ("ivanka" in record and "metrics" in record["ivanka"] and
                baseline and baseline.get("exit_code")==0 and "metrics" in baseline):
                if project_catalog is not None and getattr(args,"diagnose_project_reference",False):
                    try:
                        from project_references import aligned_to_project_reference
                        projects=project_catalog
                        ref_iva=Path(baseline.get("artifact_dir",str(RESULTS/invocation/name/"iva")))
                        ref_ivanka=Path(record["ivanka"].get("artifact_dir",str(RESULTS/invocation/name/"ivanka")))
                        record["project_reference_alignment"]=aligned_to_project_reference(
                            ref_iva,ref_ivanka,projects,row["micall_project_code"])
                    except (OSError,KeyError,ValueError) as exc:
                        record["project_reference_error"]=str(exc)
                        # Project-specific remap is diagnostic only; the panel is authoritative.
                from reference_panel import panel_acceptance
                iva_dir=Path(baseline.get("artifact_dir",str(RESULTS/invocation/name/"iva")))
                ivanka_dir=Path(record["ivanka"].get("artifact_dir",str(RESULTS/invocation/name/"ivanka")))
                record["best_contig_acceptance"]=panel_acceptance(
                    iva_dir,ivanka_dir,reference_panel,
                    min_ratio=alignment_score_floor(args))
                record["output_comparison"]=compare_outputs(
                    baseline["metrics"],record["ivanka"]["metrics"])
                iva_depth=baseline["metrics"].get("coverage_depth")
                ivanka_depth=record["ivanka"]["metrics"].get("coverage_depth")
                if iva_depth and ivanka_depth:
                    record["coverage_comparison"]={
                        "iva":iva_depth,
                        "ivanka":ivanka_depth,
                        "covered_position_delta":(
                            ivanka_depth["covered_positions"]-
                            iva_depth["covered_positions"]),
                        "ge_10_position_delta":(
                            ivanka_depth["positions_ge_10"]-
                            iva_depth["positions_ge_10"]),
                    }
                if not record["best_contig_acceptance"]["pass"]:
                    failures+=1
            else:
                record["evaluation_error"]="Missing valid IVA baseline or completed Ivanka MiCall outputs"
                failures+=1
    except Exception as exc:
        record["status"]="error"
        record["error"]=f"{type(exc).__name__}: {exc}"
        failures+=1
    if record["status"]=="started":
        record["status"]="finished"
    record["failed"]=bool(failures)
    record["total_seconds"]=round(time.monotonic()-started,2)
    record["sample_time_limit_seconds"]=getattr(args,"sample_time_limit",1800)
    # For formal 198 qualification the cap is on each complete Podman
    # container lifetime, not on subsequent host-side alignment scoring.
    if getattr(args, "qualify_198", False):
        # IVA-only control preparation is not a paired qualification. Check
        # the executed arms here; the strict verifier separately requires both.
        arms_present = [arm for arm in ("iva", "ivanka") if arm in record]
        cap_ok = bool(arms_present) and all(
            isinstance(record[arm], dict)
            and qualification_within_cap(record["sample_time_limit_seconds"],
                                         record[arm].get("container_wall_seconds"))
            for arm in arms_present)
    else:
        cap_ok = qualification_within_cap(record["sample_time_limit_seconds"],
                                          record["total_seconds"])
    if not cap_ok:
        record["status"]="sample_timeout"
        record["failed"]=True
    return record


def failure_category(record):
    if not record.get('failed'): return None
    if record.get('status')=='sample_timeout': return 'sample_timeout'
    iva=record.get('iva')
    if not isinstance(iva,dict): return 'missing_iva_baseline'
    if iva.get('exit_code')!=0: return 'iva_pipeline_error'
    if (iva.get('metrics',{}).get('num_final_max_conseqs') or 0)==0: return 'iva_no_final_max'
    ivanka=record.get('ivanka')
    if not isinstance(ivanka,dict): return 'missing_ivanka_run'
    if ivanka.get('exit_code')!=0: return 'ivanka_pipeline_error'
    if (ivanka.get('metrics',{}).get('num_final_max_conseqs') or 0)==0: return 'ivanka_no_final_max'
    if record.get('best_contig_acceptance',{}).get('pass') is False: return 'ivanka_below_noninferiority_threshold'
    return 'other_evaluation_error'

def validate_milestone198_preflight(args, sample_count, manifest_hash, iva_image_id):
    """Fail closed before any qualification or strict cache audit."""
    if iva_image_id != milestone198.IVA_IMAGE_SHA256:
        raise ValueError("198-sample milestone requires the immutable original IVA image")
    expected=os.environ.get("IVANKA_EXPECTED_MANIFEST_SHA256", "")
    # Cache audit is read-only; it may inspect IVA without starting an IVA arm.
    cache_mode = args.cache_status and args.mode in ("iva", "ivanka")
    # Ten workers is a throughput target, not an immutable scientific gate.
    # Fewer concurrent Podman writers mitigate database-lock contention.
    if ((args.mode != "ivanka" and not cache_mode) or
        args.sample is not None or args.allow_missing_baseline or
        not args.all_projects or args.parallel_arms or not (1 <= args.jobs <= 10) or
        sample_count != milestone198.SAMPLE_COUNT or
        manifest_hash != milestone198.MANIFEST_SHA256 or
        (expected and expected != milestone198.MANIFEST_SHA256)):
        raise ValueError("198-sample milestone requires the pinned full cohort, IVA cache, all projects, and 1..10 workers; execution must be Ivanka-only")


def validate_milestone198_panel(reference_count, reference_sha256):
    if reference_count != 33 or reference_sha256 != milestone198.PANEL_SHA256:
        raise ValueError("198-sample panel differs from the frozen 33-reference panel")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", action="append",
                        help="Run only a selected sample ID (repeatable)")
    parser.add_argument("--mode", choices=("both","iva","ivanka"), default="ivanka")
    parser.add_argument("--jobs", type=int, default=10,
                        help="Independent sample pipelines to run concurrently")
    parser.add_argument("--parallel-arms", action="store_true",
                        help="Run IVA and Ivanka concurrently within each sample")
    parser.add_argument("--allow-missing-baseline", action="store_true",
                        help="Ivanka-only diagnostic: run full MiCall without control, never claim pass")
    parser.add_argument("--timeout-per-arm", type=int, default=1780,
                        help="Per-arm bound, further limited by the shared per-sample deadline")
    parser.add_argument("--sample-time-limit", type=int, default=1800,
                        help="Maximum elapsed seconds for EACH sample, including both MiCall arms and scoring")
    parser.add_argument("--qualify",action="store_true", help="Strict 18-sample IVA-eligible alpha run requiring pinned manifest and IVA eligibility evidence")
    parser.add_argument("--qualify-198",action="store_true",
                        help="Strict 198-sample alignment and runtime signed-power PSI milestone")
    parser.add_argument("--diagnostic-90-floor", action="store_true",
                        help="Use the strict milestone's 90%% score floor for selected-sample diagnostics; NOT formal 198 qualification")
    parser.add_argument("--diagnose-project-reference",action="store_true",
                        help="Optional expensive legacy IVA-selected project reference diagnostic; not used for acceptance")
    parser.add_argument("--all-projects",action="store_true",
                        help="Symmetrically enable MiCall --all_projects for IVA and Ivanka; recorded in baseline provenance")
    parser.add_argument("--import-iva-from", action="append", default=[],
                        help="Import verified IVA controls from prior result directories (never run IVA)")
    parser.add_argument("--cache-status", action="store_true",
                        help="Show verified/missing IVA baselines without running analyses")
    parser.add_argument("--probe",action="store_true")
    args=parser.parse_args()
    if args.jobs<1 or not 1<=args.sample_time_limit<=1800 or args.timeout_per_arm<1:
        parser.error("jobs and arm timeout must be positive; sample limit must be 1..1800 seconds")
    images={"iva":IVA_IMAGE,"ivanka":IVANKA_IMAGE}
    checked={}
    for arm,img in images.items():
        if args.mode not in ("both",arm): continue
        checked[arm]=image_id(img)
    # Even Ivanka-only runs must verify the exact IVA image that produced the
    # baseline; image tags by themselves are not immutable.
    pinned_iva_id = checked.get("iva") or image_id(IVA_IMAGE)
    images = pinned_run_images(images, checked, pinned_iva_id)
    if "ivanka" in checked:
        verify_identical_micall_base(images["iva"], images["ivanka"])
        verify_ivanka_image_binding(images["ivanka"])
    with (DATA/"manifest.tsv").open(newline="") as manifest:
        rows=list(csv.DictReader(manifest,delimiter="\t"))
    manifest_sample_count=len(rows)
    names=[row["sample"] for row in rows]
    if len(set(names))!=len(names):
        raise ValueError("Duplicate sample identities in manifest")
    manifest_hash=sha(DATA/"manifest.tsv")
    if args.qualify and args.diagnostic_90_floor:
        raise ValueError("18-sample alpha qualification retains its 95% floor")
    if args.qualify and args.qualify_198:
        parser.error("--qualify and --qualify-198 are mutually exclusive")
    if args.qualify_198:
        validate_milestone198_preflight(args, manifest_sample_count, manifest_hash,
                                       pinned_iva_id)
    if args.qualify:
        expected=os.environ.get("IVANKA_EXPECTED_MANIFEST_SHA256", "")
        if args.mode!="ivanka" or args.sample is not None or manifest_sample_count!=QUALIFY_SAMPLE_COUNT:
            raise ValueError("Cached-IVA qualification requires all 18 predeclared IVA-eligible samples in one Ivanka-only invocation")
        if not expected or manifest_hash!=expected:
            raise ValueError("Qualification manifest SHA-256 missing or mismatched")
        eligibility = verify_iva_eligibility(manifest_hash, names)
    else:
        eligibility = {}
    rows=[row for row in rows if args.sample is None or row["sample"] in args.sample]
    if not rows: raise ValueError("No samples selected")
    if args.import_iva_from:
        imported = import_iva_baselines(args.import_iva_from, rows, pinned_iva_id,
                                        sha(DATA/"hxb2.fasta"), args.all_projects)
        print("IVA_CACHE_IMPORT", json.dumps(imported), flush=True)
    if args.cache_status or (args.mode=="ivanka" and not args.allow_missing_baseline):
        status = iva_cache_status(rows, pinned_iva_id, sha(DATA/"hxb2.fasta"),
                                  args.all_projects, require_internal_timing=(args.qualify or args.qualify_198))
        print("IVA_CACHE_STATUS", json.dumps(status, sort_keys=True), flush=True)
        if args.cache_status:
            if args.qualify_198 and not status["missing_or_invalid"]:
                # Cache-only qualification must also authenticate the frozen panel.
                with (DATA/"hxb2.fasta").open() as reference_file:
                    frozen_hxb2=next(SeqIO.parse(reference_file,"fasta")).seq
                frozen_projects,_=load_micall_projects(images["iva"])
                from reference_panel import build_reference_panel,panel_sha256
                frozen_panel=build_reference_panel(frozen_projects,frozen_hxb2)
                validate_milestone198_panel(len(frozen_panel),panel_sha256(frozen_panel))
            return 0 if not status["missing_or_invalid"] else 2
        if status["missing_or_invalid"]:
            raise ValueError("Missing verified IVA baselines: import successful existing IVA outputs before running Ivanka")
    with (DATA/"hxb2.fasta").open() as reference_file:
        hxb2=next(SeqIO.parse(reference_file,"fasta")).seq
    projects,catalog_hash=load_micall_projects(images["iva"])
    from reference_panel import build_reference_panel,panel_sha256
    references=build_reference_panel(projects,hxb2)
    reference_panel_hash=panel_sha256(references)
    if args.qualify_198:
        validate_milestone198_panel(len(references),reference_panel_hash)
    if args.probe:
        print(json.dumps({"images":checked,"sample_count":len(rows),
                          "hxb2_sha256":sha(DATA/"hxb2.fasta"),
                          "project_reference_catalog_sha256":catalog_hash,
                          "reference_panel_sha256":reference_panel_hash,
                          "reference_panel_count":len(references)},indent=2))
        return 0
    RESULTS.mkdir(parents=True,exist_ok=True)
    invocation=str(int(time.time()))+"-"+str(os.getpid())
    hxb2_hash=sha(DATA/"hxb2.fasta")
    path=RESULTS/"results.jsonl"
    failed=0
    completed_records=[]
    benchmark_start=time.monotonic()
    with path.open("a",buffering=1) as out:
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures={}
            for row in rows:
                out.write(json.dumps({"sample":row["sample"],
                                      "invocation":invocation,"status":"started"})+"\n")
                task=executor.submit(evaluate_sample,row,args,images,checked,
                                     pinned_iva_id,hxb2_hash,hxb2,projects,invocation,reference_panel=references)
                futures[task]=row["sample"]
            for task in as_completed(futures):
                name=futures[task]
                try:
                    record=task.result()
                except Exception as exc:
                    record={"sample":name,"invocation":invocation,"status":"error",
                            "error":f"{type(exc).__name__}: {exc}","failed":True}
                out.write(json.dumps(record,sort_keys=True)+"\n")
                completed_records.append(record)
                if record["failed"]:
                    failed+=1
                print(name,record["status"],"fail" if record["failed"] else "ok",
                      record.get("best_contig_acceptance",{}),flush=True)
    accepted=sum(r.get("best_contig_acceptance",{}).get("pass") is True
                 for r in completed_records)
    finished_names=[r.get("sample") for r in completed_records]
    both_arms_complete=all(
        r.get("status")=="finished" and
        r.get("iva",{}).get("exit_code")==0 and
        r.get("ivanka",{}).get("exit_code")==0 and
        "metrics" in r.get("iva",{}) and "metrics" in r.get("ivanka",{})
        for r in completed_records)
    cached_arms_complete=all(
        r.get("status")=="finished" and
        r.get("iva_baseline_reused") is True and
        r.get("iva",{}).get("exit_code")==0 and
        r.get("ivanka",{}).get("exit_code")==0 and
        "metrics" in r.get("iva",{}) and "metrics" in r.get("ivanka",{})
        for r in completed_records)
    full_scope=(args.qualify and len(rows)==QUALIFY_SAMPLE_COUNT and
                len(completed_records)==QUALIFY_SAMPLE_COUNT and
                len(set(finished_names))==QUALIFY_SAMPLE_COUNT and
                set(finished_names)==set(names) and
                (both_arms_complete if args.mode=="both" else cached_arms_complete) and
                all("best_contig_acceptance" in r for r in completed_records))
    global_seconds=time.monotonic()-benchmark_start
    max_sample_seconds=max((r["total_seconds"] for r in completed_records
                            if isinstance(r.get("total_seconds"), (int,float))), default=None)
    container_walls = [
        r[arm].get("container_wall_seconds")
        for r in completed_records for arm in ("iva", "ivanka")
        if isinstance(r.get(arm), dict)]
    max_container_wall_seconds = max(
        (w for w in container_walls if milestone198.finite(w, positive=True)),
        default=None)
    per_sample_timing_complete=all(
        isinstance(r.get("total_seconds"),(int,float)) for r in completed_records)
    if args.qualify_198:
        per_sample_timing_complete = (per_sample_timing_complete and
            len(container_walls) == 2 * len(completed_records) and
            all(qualification_within_cap(args.sample_time_limit,w)
                for w in container_walls))
    qualification_elapsed = (max_container_wall_seconds if args.qualify_198
                             else max_sample_seconds)
    complete_noninferiority=(full_scope and per_sample_timing_complete and
                            qualification_within_cap(args.sample_time_limit,qualification_elapsed)
                            and accepted==manifest_sample_count and failed==0)
    # Preserve the distinction: cached controls are not a same-invocation IVA/IVANKA run.
    full_alpha_pass=(complete_noninferiority and args.mode=="both")
    cached_iva_comparison_pass=(complete_noninferiority and args.mode=="ivanka")
    reason_counts={}
    for record in completed_records:
        reason=failure_category(record)
        if reason is not None:
            reason_counts[reason]=reason_counts.get(reason,0)+1
    summary={
        "invocation":invocation,"mode":args.mode,"images":checked,
        "iva_baseline_image_id":pinned_iva_id,
        "iva_baseline_cache_dir":str(IVA_BASELINE_CACHE),
        "hxb2_sha256":hxb2_hash,"manifest_sha256":manifest_hash,
        "project_reference_catalog_sha256":catalog_hash,
        "qualification_requested":args.qualify or args.qualify_198,
        "qualification198_requested":args.qualify_198,
        "all_projects":getattr(args,"all_projects",False),
        "manifest_sample_count":manifest_sample_count,
        "selected_samples":len(rows),"finished_samples":len(completed_records),
        "accepted_samples":accepted,
        "failed_samples":[r["sample"] for r in completed_records if r["failed"]],
        "failure_categories":reason_counts,
        "global_seconds":round(global_seconds,2),
        "sample_limit_seconds":args.sample_time_limit,
        "max_sample_seconds":(round(max_sample_seconds,2) if max_sample_seconds is not None else None),
        "max_container_wall_seconds":(round(max_container_wall_seconds,2)
                                      if max_container_wall_seconds is not None else None),
        "reference_panel_sha256":reference_panel_hash,
        "reference_panel_count":len(references),
        **eligibility,
        "jobs":args.jobs,"parallel_arms":args.parallel_arms,
        "allow_missing_baseline":args.allow_missing_baseline,
        "full_alpha_pass":full_alpha_pass,
        "cached_iva_comparison_pass":cached_iva_comparison_pass,
        "note":"Cached-IVA qualification requires all original 18 eligible samples, individually verified immutable IVA controls, one Ivanka-only invocation, and 1800 seconds per sample. It is distinct from same-invocation two-arm qualification."
    }
    if args.qualify_198:
        summary.update(milestone198.qualify(
            completed_records,names,pinned_iva_id,checked["ivanka"],
            args.sample_time_limit,reference_panel_hash))
    (RESULTS/f"summary-{invocation}.json").write_text(
        json.dumps(summary,indent=2,sort_keys=True))
    if not args.qualify_198:
        print("CACHED_IVA_QUALIFICATION_PASS" if cached_iva_comparison_pass else ("FULL_ALPHA_PASS" if full_alpha_pass else "QUALIFICATION_NOT_PASSED"),
              f"{accepted}/{manifest_sample_count} full-pipeline comparisons",
              flush=True)
    if args.qualify_198:
        print("MILESTONE_198_PASS" if summary["milestone198_pass"] else "MILESTONE_198_NOT_PASSED",
              "198/198 required, score and runtime PSI(0,1,2) strictly positive",flush=True)
        return 0 if summary["milestone198_pass"] else 1
    return 1 if failed or (args.qualify and not (full_alpha_pass or cached_iva_comparison_pass)) else 0

if __name__=="__main__":
    raise SystemExit(main())
