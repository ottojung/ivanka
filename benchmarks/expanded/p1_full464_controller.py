"""Supervised full-464 Ivanka candidate controller.

The controller measures only the candidate Ivanka arm with the frozen MiCall
pipeline and reuses every other arm from the attested original results file.
Hidden truth is used solely by the post-assembly scorer and never enters the
container. Each case is sealed before scratch is retired; failures keep their
scratch and logs for diagnosis.
"""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from benchmarks.assembler_bench.sam_metrics import public_diagnostics
from benchmarks.podman_full_micall import score_outputs
from benchmarks.psi_acceptance import summarize as psi_summarize
from benchmarks.retained_artifacts import (
    seal_terminal_evidence,
    terminal_retire,
)
from .gate_multitruth import check_sample
from .micall_dominant import (
    MULTITRUTH_SCORE_ORIGIN,
    evaluate_final_alignment,
)
from .micall_synthetic_constants import TIMING_ORIGIN

SCHEMA = "ivanka.p1.full464.candidate-controller.v1"
STATUS = "ATTEMPTED_NOT_QUALIFIED"
FLOOR = 0.90
WALL_CAP_SECONDS = 2400
PODMAN_TIMEOUT_SECONDS = 2398
MEMORY_BYTES = 4_000_000_000
RESERVE_GIB = 32
ADMISSION_GIB = 2
DEFAULT_LOCK = "/workspace/ivanka-p1-component-image-20261124/pilot.lock"
DEFAULT_DATA = "/workspace/ivanka-synthetic-abundance15-464-20261117"
DEFAULT_FROZEN = (
    "/workspace/micall-frozen-seven-20261117/phase-synthetic464/results.jsonl"
)
DEFAULT_TIMER = (
    "/workspace/micall-frozen-seven-20261117/ivanka-physical-source/"
    "benchmarks/inside_container_timing.py"
)
DEFAULT_STORAGE_CONF = (
    "/workspace/ivanka-podman-overlay-20261103/storage.conf"
)
DEFAULT_IMAGE = (
    "6fba70953664b95c3357c65d80fa56f0563962d0ff0112fa97e43ddd10a70971"
)
DEFAULT_COMMIT = "12d8c72f01f305b7f81db26193ec5fc213ba55bf"
ORIGINAL_IVANKA_IMAGE = (
    "da795bbdbfbdd3c735c59d0ee008dae1781c68268b24298235e6b2cfe50a23ad"
)
PINS = {
    "cohort.json": (
        "90990f6109553347d37f7754cde63398a4dce57c388f90c2ce4b648530bfdfe4"
    ),
    "phase-synthetic464/results.jsonl": (
        "7e1e81ce253fec2e4052db4843bfc580491c89bbc320a21374058f4297482203"
    ),
    "gate_multitruth.py": (
        "03290864ac2aad23b1a0a8d7054c94291ae1f9602588f5241158f913895ba9f6"
    ),
    "inside_container_timing.py": (
        "c5baab15b8c54f27b5cfbaf459f8647707e1e9618577b803ee3440e3e661eb4e"
    ),
}


def sha256(path):
    """Hash a file without materializing it in memory."""
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path, payload):
    """Commit a JSON document with fsync so a crash cannot leave half a receipt."""
    path = Path(path)
    temporary = path.with_name("." + path.name + ".part")
    with temporary.open("x") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def atomic_append(path, row):
    """Append one complete JSONL record and flush it before returning."""
    with Path(path).open("a", buffering=1) as stream:
        stream.write(json.dumps(row, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


@contextlib.contextmanager
def single_worker(lock_path):
    """Share the operator pilot lock so no second benchmark worker can start."""
    path = Path(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def podman_env(storage_conf):
    env = os.environ.copy()
    if storage_conf:
        env["CONTAINERS_STORAGE_CONF"] = str(storage_conf)
    return env


def podman_inspect(image, env, fmt="{{json .Config.Labels}}"):
    result = subprocess.run(
        ["podman", "image", "inspect", "--format", fmt, image],
        env=env, capture_output=True, text=True, timeout=60, check=False,
    )
    return result


def verify_candidate_image(image, commit, env):
    """Bind the immutable image to its source commit before any case runs."""
    if len(image) != 64 or any(c not in "0123456789abcdef" for c in image):
        raise ValueError("candidate image must be a full immutable SHA-256")
    if image == ORIGINAL_IVANKA_IMAGE:
        raise ValueError("original frozen Ivanka image may not be rerun")
    if not subprocess.run(["podman", "image", "exists", image], env=env,
                          check=False).returncode == 0:
        raise ValueError("candidate image is not installed locally")
    identifier = podman_inspect(image, env, "{{.Id}}")
    if identifier.returncode != 0 or identifier.stdout.strip().removeprefix(
            "sha256:") != image:
        raise ValueError("candidate image identity differs from its digest")
    labels = json.loads(podman_inspect(image, env).stdout)
    if labels.get("org.ottojung.ivanka.source-commit") != commit:
        raise ValueError("candidate image source-commit label differs")
    if labels.get("org.ottojung.micall.frozen-image-id") != (
            ORIGINAL_IVANKA_IMAGE):
        raise ValueError("candidate image does not inherit the frozen MiCall image")
    frozen_manifest = labels.get("org.ottojung.ivanka.frozen-manifest-sha256")
    if frozen_manifest != (
        "9db6e1b569b17aed8b7e96abea495b09374e609478834371e2943b16df36884f"
    ):
        raise ValueError("candidate image does not inherit the frozen manifest")
    return labels


def build_command(case_dir, output_dir, image, timer, container_name):
    """Mirror the operator's exact integrated MiCall command for one arm."""
    return [
        "podman", "run", "--rm", "--pull=never", "--network=none",
        "--userns=host", "--cpus=2", "--memory=" + str(MEMORY_BYTES),
        "--name", container_name, "--timeout", str(PODMAN_TIMEOUT_SECONDS),
        "--stop-timeout", "2",
        "-v", str(Path(case_dir) / "reads") + ":/reads:ro",
        "-v", str(output_dir) + ":/results:rw",
        "-v", str(timer) + ":/ivanka-timer.py:ro",
        "--entrypoint", "/opt/venv/bin/python", image,
        "/ivanka-timer.py", "/results/timing.json",
        "micall", "analyze", "sample",
        "/reads/R1.fastq.gz", "/reads/R2.fastq.gz", "/results",
        "--denovo", "--keep_scratch", "--bad_cycles_csv",
        "/results/bad_cycles.csv", "--all_projects",
    ]


FORBIDDEN_MOUNT_TOKENS = (
    "hidden-truth", "hidden_truth", "haplotypes.fasta", "hxb2",
    "reference", "truth", "panel",
)


def assert_reference_blind(command):
    """Refuse any argv or mount that could leak truth into the assembler."""
    for argument in command:
        lowered = str(argument).lower()
        if any(token in lowered for token in FORBIDDEN_MOUNT_TOKENS):
            raise ValueError("reference or truth reached the assembler argv")
    mounts = [command[index + 1] for index, item in enumerate(command[:-1])
              if item == "-v"]
    if len(mounts) != 3 or not mounts[0].endswith(":/reads:ro") or not (
            mounts[1].endswith(":/results:rw")) or not mounts[2].endswith(
            ":/ivanka-timer.py:ro"):
        raise ValueError("unexpected integrated MiCall mount contract")
    if "/reads/R1.fastq.gz" not in command or "/reads/R2.fastq.gz" not in command:
        raise ValueError("missing original paired reads")


def input_fingerprint(case_hashes):
    """Reuse the original cohort's two-mate identity contract."""
    return hashlib.sha256((case_hashes["reads/R1.fastq.gz"] +
                           case_hashes["reads/R2.fastq.gz"]).encode()).hexdigest()


def verify_case_hashes(case_dir, case_hashes):
    for name, expected in case_hashes.items():
        actual = sha256(Path(case_dir) / name)
        if actual != expected:
            raise ValueError(f"{name}: input hash changed")
    return dict(case_hashes)


def rss_tree(pid, env):
    """Conservatively sum sampled RSS over a process and all descendants."""
    rows = subprocess.check_output(
        ["ps", "-eo", "pid=,ppid=,rss="], env=env, text=True).splitlines()
    children = {}
    resident = {}
    for line in rows:
        process_id, parent_id, kilobytes = map(int, line.split())
        children.setdefault(parent_id, []).append(process_id)
        resident[process_id] = kilobytes
    pending = [pid]
    seen = set()
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        pending.extend(children.get(current, []))
    return sum(resident.get(value, 0) for value in seen) * 1024


def container_dead(container_name, env):
    result = subprocess.run(["podman", "container", "exists", container_name],
                            env=env, check=False)
    return result.returncode == 1


def disk_admission(root, reserve_gib=RESERVE_GIB, allocation_gib=ADMISSION_GIB):
    """Fail closed before a case starts; leave the reserve plus staged budget."""
    free = shutil.disk_usage(str(root)).free
    needed = (reserve_gib + allocation_gib) * 1024 ** 3
    if free < needed:
        raise RuntimeError(f"disk admission: {free} free < {needed} required")
    return free


def load_frozen(frozen_path, expected_hash, cohort_hashes):
    """Reuse original rival evidence by hash-attested readback, never rerun."""
    actual = sha256(frozen_path)
    if actual != expected_hash:
        raise ValueError("frozen results file hash differs from pin")
    rows = {}
    for line in Path(frozen_path).read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rows[row["id"]] = row
    if set(rows) != set(cohort_hashes):
        raise ValueError("frozen results do not match the pinned 464 cohort")
    return rows, actual


def assemble_row(case_id, candidate, frozen_row, frozen_hash, case_hashes,
                 truth_validation, family, candidate_commit, image):
    """Combine a fresh Ivanka arm with unchanged rival measurements."""
    rivals = {}
    for name, arm in frozen_row["results"].items():
        if name == "ivanka":
            continue
        rivals[name] = {
            **arm,
            "reused_from": {
                "schema": "ivanka.p1.frozen-arm-reuse.v1",
                "case_id": case_id,
                "results_sha256": frozen_hash,
                "image_sha256": arm.get("sha256"),
            },
        }
    return {
        "id": case_id,
        "cohort": "synthetic",
        "family": family,
        "truth_validation": truth_validation,
        "input_sha256": input_fingerprint(case_hashes),
        "results": {"ivanka": candidate, **rivals},
        "provenance": {
            "schema": SCHEMA,
            "status": STATUS,
            "candidate_source_commit": candidate_commit,
            "candidate_image": image,
            "frozen_results_sha256": frozen_hash,
            "original_arms_rerun": False,
        },
    }


def candidate_source_hashes(folder, case_hashes, image, extra=None):
    """Seal the complete input contract for terminal retirement."""
    hashes = dict(extra or {})
    hashes["image_id"] = image
    for name in ("timing.json", "argv.json", "bad_cycles.csv", "podman.log"):
        path = Path(folder) / name
        if path.is_file():
            hashes[name] = sha256(path)
    hashes.update(case_hashes)
    return hashes


def load_committed(folder, case_hashes, image):
    """Return a committed row only when every receipt still verifies."""
    receipt_path = Path(folder) / "receipt.json"
    case_path = Path(folder) / "case.json"
    if not receipt_path.is_file() or not case_path.is_file():
        return None
    receipt = json.loads(receipt_path.read_text())
    row = json.loads(case_path.read_text())
    if receipt.get("receipt_sha256") != sha256(case_path):
        raise ValueError("committed case receipt digest differs")
    if receipt.get("image") != image:
        raise ValueError("committed candidate image differs")
    if receipt.get("case_hashes") != case_hashes:
        raise ValueError("committed case inputs differ")
    candidate = row.get("results", {}).get("ivanka", {})
    if candidate.get("sha256") != image:
        raise ValueError("committed candidate arm image differs")
    evidence = Path(folder) / "terminal_evidence.json"
    sidecar = Path(folder) / "terminal_evidence.json.sha256"
    if candidate.get("status") == "success":
        if not evidence.is_file() or not sidecar.is_file():
            raise ValueError("successful arm lacks sealed terminal evidence")
        if sidecar.read_text().strip() != sha256(evidence):
            raise ValueError("sealed terminal evidence hash changed")
        sealed = json.loads(evidence.read_text())
        if sealed.get("schema") != "ivanka.retention.terminal.v1" or not (
                sealed.get("sealed") is True):
            raise ValueError("terminal evidence is not sealed")
    return row


def terminal_retirement(folder, candidate, success, source_hashes, env):
    """Seal exact scoring evidence, then retire only a verified live tree."""
    path = Path(folder)
    if success:
        metrics = score_outputs(path, None)
        diagnostics = public_diagnostics(path)
        evidence = {
            "metrics": metrics,
            "public_diagnostics": diagnostics,
            "candidate": candidate,
        }
    else:
        log = path / "podman.log"
        evidence = {"failure": {
            "exit_code": candidate.get("exit_code"),
            "error": candidate.get("error"),
            "error_tail": log.read_text()[-1200:] if log.is_file() else "",
            "container_wall_seconds": candidate.get("wall_seconds"),
        }}
    evidence_path, _ = seal_terminal_evidence(path, evidence, source_hashes)
    if not success:
        return {"applied": False, "reason": "failure scratch preserved",
                "evidence": evidence_path.name}
    def dead():
        return container_dead(candidate["container_name"], env)
    return terminal_retire(path, evidence_path=evidence_path,
                           container_dead=dead,
                           source_hashes=source_hashes)


def evaluate(records):
    """Pinned 0.90 floors and strict all-r Psi on complete valid pairs only."""
    rows = list(records)
    errors = []
    if len(rows) != 464 or len({row["id"] for row in rows}) != 464:
        errors.append("expected exactly 464 unique synthetic cases")
    per_case = []
    for row in rows:
        results = row.get("results", {})
        ivanka = results.get("ivanka", {})
        rivals = {name: arm for name, arm in results.items() if name != "ivanka"}
        available = [name for name, arm in rivals.items()
                     if arm.get("status") == "success"
                     and isinstance(arm.get("per_truth"), dict)
                     and arm.get("per_truth")]
        failed = [name for name, arm in rivals.items()
                  if arm.get("status") != "success"]
        case_errors = []
        if ivanka.get("status") != "success":
            case_errors.append("candidate_not_success")
        if available:
            if ivanka.get("status") == "success":
                best = max(rivals[name]["score"] for name in available)
                if ivanka["score"] + 1e-7 < FLOOR * best:
                    case_errors.append("below_90pct_best_available_rival")
            checked = {"ivanka": ivanka,
                       **{name: rivals[name] for name in available}}
            case_errors.extend(check_sample(
                row["id"], checked, available, FLOOR))
        else:
            case_errors.append("no_complete_rival_for_comparison")
        per_case.append({
            "id": row["id"], "family": row.get("family"),
            "errors": case_errors, "failed_rivals": sorted(failed),
            "available_rivals": sorted(available),
            "candidate_score": ivanka.get("score"),
            "best_rival_score": max(
                (rivals[name]["score"] for name in available
                 if isinstance(rivals[name].get("score"), (int, float))),
                default=None),
        })
        errors.extend(f"{row['id']}:{error}" for error in case_errors)
    psi = {}
    for rival in sorted({name for row in rows for name in row.get("results", {})
                         if name != "ivanka"}):
        scores = []
        runtimes = []
        for row in rows:
            arms = row.get("results", {})
            first, second = arms.get("ivanka"), arms.get(rival)
            if not first or not second or first.get("status") != "success" or (
                    second.get("status") != "success"):
                continue
            if not all(isinstance(arm.get("seconds"), (int, float))
                       and arm["seconds"] > 0 for arm in (first, second)):
                continue
            scores.append(first["score"] - second["score"])
            runtimes.append(second["seconds"] - first["seconds"])
        if not scores:
            psi[rival] = {"complete_pairs": 0, "status": "incomplete"}
            continue
        try:
            score_psi = psi_summarize(scores)
            runtime_psi = psi_summarize(runtimes)
        except ValueError as exc:
            psi[rival] = {"complete_pairs": len(scores),
                          "status": "unresolved", "error": str(exc)}
            continue
        psi[rival] = {
            "complete_pairs": len(scores),
            "status": "positive_all_r" if (
                score_psi["positive_all_nonnegative"]
                and runtime_psi["positive_all_nonnegative"]) else "not_positive_all_r",
            "score_psi": score_psi, "runtime_psi": runtime_psi,
        }
    return {
        "schema": "ivanka.p1.synthetic-candidate-evaluation.v1",
        "status": STATUS,
        "qualification_claim": "NONE",
        "floor": FLOOR,
        "cases": len(rows),
        "pass": not errors and all(item["status"] == "positive_all_r"
                                   for item in psi.values()),
        "errors": errors,
        "per_case": per_case,
        "all_r_psi": psi,
    }


def run(args):
    """Execute one supervised candidate arm per case and verify the result."""
    data = Path(args.data).resolve()
    frozen_path = Path(args.frozen_results).resolve()
    timer = Path(args.timer).resolve()
    gate = Path(args.gate).resolve()
    output = Path(args.out).resolve()
    env = podman_env(args.storage_conf)
    if args.resume:
        output.mkdir(parents=True, exist_ok=True)
    else:
        output.mkdir(parents=True, exist_ok=False)
    for path, pin in ((data / "cohort.json", PINS["cohort.json"]),
                      (frozen_path, PINS["phase-synthetic464/results.jsonl"]),
                      (gate, PINS["gate_multitruth.py"]),
                      (timer, PINS["inside_container_timing.py"])):
        if sha256(path) != pin:
            raise ValueError(f"source hash gate failed for {path}")
    labels = verify_candidate_image(args.image, args.commit, env)
    cohort = json.loads((data / "cohort.json").read_text())
    case_hashes = {entry["id"]: entry["sha256"] for entry in cohort["cases"]}
    if len(case_hashes) != 464:
        raise ValueError("full 464-case mixed-viral cohort required")
    frozen, frozen_hash = load_frozen(
        frozen_path, PINS["phase-synthetic464/results.jsonl"], case_hashes)
    truth_validation = frozen[next(iter(case_hashes))]["truth_validation"]
    selected = args.cases.split(",") if args.cases else list(case_hashes)
    if args.limit is not None:
        selected = selected[:args.limit]
    if any(case not in case_hashes for case in selected):
        raise ValueError("unknown selected case")
    if len(set(selected)) != len(selected):
        raise ValueError("duplicate selected case")
    manifest = {
        "schema": SCHEMA, "status": STATUS, "qualified": False,
        "candidate_source_commit": args.commit,
        "candidate_image": args.image,
        "candidate_image_labels": labels,
        "frozen_results_sha256": frozen_hash,
        "pins": PINS, "policy": {
            "wall_cap_seconds": WALL_CAP_SECONDS,
            "podman_timeout_seconds": PODMAN_TIMEOUT_SECONDS,
            "memory_bytes": MEMORY_BYTES,
            "reserve_gib": RESERVE_GIB,
            "allocation_gib": ADMISSION_GIB,
        },
        "selected_cases": selected,
    }
    manifest_path = output / "run_manifest.json"
    if args.resume:
        if json.loads(manifest_path.read_text()) != manifest:
            raise ValueError("resume manifest/image/policy mismatch")
    else:
        atomic_json(manifest_path, manifest)
    results_path = output / "results.jsonl"
    completed = []
    with single_worker(args.lock):
        for case_id in selected:
            case_dir = data / case_id
            destination = output / case_id
            hashes = case_hashes[case_id]
            recovered = load_committed(destination, hashes, args.image) if (
                args.resume and destination.exists()) else None
            if recovered is not None:
                completed.append(recovered)
                print("P1_CASE_RECOVERED", case_id, flush=True)
                continue
            if destination.exists():
                interrupted = output / "_interrupted"
                interrupted.mkdir(exist_ok=True)
                target = interrupted / case_id
                suffix = 1
                while target.exists():
                    suffix += 1
                    target = interrupted / f"{case_id}-{suffix:03d}"
                destination.rename(target)
            disk_admission(output.parent, args.reserve_gib, args.allocation_gib)
            verify_case_hashes(case_dir, hashes)
            destination.mkdir(parents=True, exist_ok=False)
            (destination / "bad_cycles.csv").write_text("tile,cycle\n")
            name = "ivanka-p1-full464-" + hashlib.sha256(
                (case_id + ":" + args.image).encode()).hexdigest()[:18]
            command = build_command(case_dir, destination, args.image, timer, name)
            assert_reference_blind(command)
            atomic_json(destination / "argv.json", command)
            source_hashes = candidate_source_hashes(
                destination, hashes, args.image)
            record = {
                "status": "failed", "score": 0.0,
                "score_origin": MULTITRUTH_SCORE_ORIGIN,
                "timing_origin": TIMING_ORIGIN,
                "sha256": args.image, "container_name": name,
                "argv": command, "exit_code": None,
                "per_truth": {}, "diagnostics": {},
            }
            started = time.monotonic()
            process_pid = 0
            peak = 0
            log_path = destination / "podman.log"
            with log_path.open("wb") as log:
                process = subprocess.Popen(command, env=env, stdout=log,
                                           stderr=subprocess.STDOUT)
                while process.poll() is None:
                    if not process_pid:
                        probe = subprocess.run(
                            ["podman", "inspect", "--format", "{{.State.Pid}}",
                             name], env=env, capture_output=True, text=True,
                            check=False)
                        if probe.returncode == 0:
                            try:
                                process_pid = int(probe.stdout.strip())
                            except ValueError:
                                pass
                    if process_pid:
                        peak = max(peak, rss_tree(process_pid, env))
                    elapsed = time.monotonic() - started
                    if (peak > MEMORY_BYTES or elapsed > WALL_CAP_SECONDS
                            or shutil.disk_usage(str(output.parent)).free
                            < (RESERVE_GIB * 1024 ** 3)):
                        subprocess.run(["podman", "kill", name], env=env,
                                       capture_output=True, check=False)
                        process.wait(timeout=30)
                        break
                    time.sleep(0.5)
            wall = round(time.monotonic() - started, 6)
            record.update(returncode=process.returncode,
                          wall_seconds=wall,
                          peak_sampled_rss_bytes=peak,
                          container_dead=container_dead(name, env))
            if record["container_dead"] is not True:
                record["error"] = "container liveness could not be established"
            elif process.returncode == 0:
                try:
                    clock = json.loads((destination / "timing.json").read_text())
                    if (clock.get("timing_origin") != TIMING_ORIGIN
                            or clock.get("exit_code") != 0
                            or not isinstance(clock.get("seconds"), (int, float))
                            or clock["seconds"] <= 0
                            or clock["seconds"] > WALL_CAP_SECONDS
                            or peak <= 0 or peak > MEMORY_BYTES):
                        raise ValueError("invalid in-container timing or RSS cap")
                    metrics = evaluate_final_alignment(
                        json.loads((case_dir / "manifest.json").read_text()),
                        case_dir / hashes["hidden-truth/haplotypes.fasta"],
                        destination)
                    if metrics["score_origin"] != MULTITRUTH_SCORE_ORIGIN:
                        raise ValueError("wrong final MiCall score origin")
                    record.update(
                        status="success", seconds=clock["seconds"],
                        timing=clock, score=metrics["score"],
                        dominant_exact=metrics["dominant_exact"],
                        final_dominant=metrics["source"],
                        per_truth=metrics["source"]["per_truth"])
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    record["error"] = f"{type(exc).__name__}: {exc}"
            else:
                record["error"] = f"MiCall exited {process.returncode}"
            try:
                record["diagnostics"] = public_diagnostics(destination)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                record["diagnostics"] = {
                    "error": f"{type(exc).__name__}: {exc}"}
            source_hashes = candidate_source_hashes(
                destination, hashes, args.image, {"podman.log": sha256(log_path)})
            success = record["status"] == "success"
            record["terminal_retention"] = terminal_retirement(
                destination, record, success, source_hashes, env)
            row = assemble_row(case_id, record, frozen[case_id], frozen_hash,
                               hashes, truth_validation,
                               json.loads((case_dir / "manifest.json").read_text())[
                                   "family"], args.commit, args.image)
            atomic_json(destination / "case.json", row)
            atomic_json(destination / "receipt.json", {
                "schema": "ivanka.p1.case-receipt.v1",
                "image": args.image,
                "case_hashes": hashes,
                "receipt_sha256": sha256(destination / "case.json"),
                "terminal_retention": record["terminal_retention"],
            })
            atomic_append(results_path, row)
            completed.append(row)
            print("P1_CASE", case_id, record["status"],
                  record.get("error", ""), flush=True)
    evaluation = evaluate(completed)
    atomic_json(output / "evaluation.json", evaluation)
    atomic_json(output / "attempt_summary.json", {
        "schema": SCHEMA, "status": STATUS, "qualified": False,
        "cases_attempted": len(completed),
        "result_sha256": sha256(results_path),
        "evaluation_pass": evaluation["pass"],
    })
    return evaluation


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(DEFAULT_DATA))
    parser.add_argument("--frozen-results", type=Path,
                        default=Path(DEFAULT_FROZEN))
    parser.add_argument("--gate", type=Path,
                        default=(Path(__file__).resolve().parents[2]
                                 / "benchmarks/expanded/gate_multitruth.py"))
    parser.add_argument("--timer", type=Path, default=Path(DEFAULT_TIMER))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--commit", default=DEFAULT_COMMIT)
    parser.add_argument("--storage-conf", type=Path,
                        default=Path(DEFAULT_STORAGE_CONF))
    parser.add_argument("--lock", default=DEFAULT_LOCK)
    parser.add_argument("--cases", help="comma-separated case IDs for a smoke run")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--reserve-gib", type=int, default=RESERVE_GIB)
    parser.add_argument("--allocation-gib", type=int, default=ADMISSION_GIB)
    args = parser.parse_args(argv)
    result = run(args)
    print("P1_FULL464_CONTROLLER", STATUS, "cases", result["cases"],
          "pass", result["pass"], flush=True)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
