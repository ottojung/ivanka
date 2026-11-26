"""Bounded prospective P1 pilot controller for the combined 950fe331 candidate.

Rebased source-only entrypoint: the previous hwe8M runner (babc4dba,
"fix/p1-bounded-pilot-runner-integration") is re-based on exact PR527
``aad9a2cde61d7e8b12b44268f0135ee5060911ef``. On PR527 the shared guard
``fail_closed_guard.p1_harness.run_prospective`` already owns a REAL durable
controller heartbeat (``heartbeat.Emitter`` before spawn, ``bound(cid)`` and a
fresh refresh on every watch sample). This controller therefore does NOT inject
or override a heartbeat: it relies on the guard's real one. It adds only the
pilot-specific source pins, the matching pinned PX store binding, the 32 GiB
reserve + 1 GiB reservation admission, its owner-bound STOP and the bounded
explicit case list.

Cross-campaign exclusion is NOT provided by a pilot-private lock. This
controller must prove it operates inside the ACTUAL shared PX worker boundary
(``.global-worker.lock`` plus the watchdog's durable ``.worker-lease.jsonl``
root and its matching graphroot) or fail closed at ``--check`` time.

No live container, image build, large image import, STOP mutation, lease
creation or truth-in-assembly occurs by default. ``--check`` is read-only and
produces a prepared manifest. Execution requires ``--armed`` plus an exact
operator-issued slot token; until then this is source only.

Truth/reference files are verified but never mounted or passed to the
assembler. Post-hoc scoring happens only after the guarded container has exited
and exact teardown is proven.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import time
import tomllib
from pathlib import Path

from benchmarks.fail_closed_guard import stop as guard_stop
from benchmarks.fail_closed_guard import p1_harness
from benchmarks.fail_closed_guard.errors import GuardExceeded

from .micall_dominant import MULTITRUTH_SCORE_ORIGIN, evaluate_final_alignment
from .micall_synthetic_constants import TIMING_ORIGIN
from .p1_full464_controller import (
    ADMISSION_GIB,
    DEFAULT_DATA,
    DEFAULT_FROZEN,
    DEFAULT_TIMER,
    MEMORY_BYTES,
    ORIGINAL_IVANKA_IMAGE,
    PODMAN_TIMEOUT_SECONDS,
    PINS,
    RESERVE_GIB,
    WALL_CAP_SECONDS,
    assert_reference_blind,
    atomic_append,
    atomic_json,
    candidate_source_hashes,
    input_fingerprint,
    load_frozen,
    podman_env,
    sha256,
    verify_case_hashes,
)

SCHEMA = "ivanka.p1.bounded-pilot-controller.v2"
STATUS = "ATTEMPTED_NOT_QUALIFIED"
SOURCE_COMMIT = "950fe331dfcd857011bfd63f9eeca92462708545"
PARENT_IMAGE = ORIGINAL_IVANKA_IMAGE
INTEGRATION_BASE = "aad9a2cde61d7e8b12b44268f0135ee5060911ef"

CASES_MANIFEST = Path(__file__).with_name("p1_pilot_cases.json")
IMAGE_MANIFEST = Path(__file__).with_name("p1_pilot_image_manifest.json")
CONTAINERFILE = Path(__file__).with_name(
    "Containerfile.p1-pilot-950fe331-binary-only")

PINS_V2 = {
    "cases_manifest": "fda0e3105ec4a09869dbcd31fe199126ee5088495cd32a02c72b545a51c509de",
    "image_manifest": "29f48843d74f41b107495ae003ee65787653d9d22599dd3b3e9f7a4a2cdef13b",
    "storage_conf": "fdf5ce294ebcd8a950d1ae2016032a2620e9b16cabf33c772dc43ab425ecec21",
    "physical_spec": "478c1b7b68943ac5e1ef565c257fd96ba6871184425ace80b026dd2b18cf8f87",
}

# Operator-admission policy: 32 GiB independent reserve plus a 1 GiB
# reservation, i.e. >= 33 GiB free on the shared workspace before any arm.
PILOT_RESERVE_GIB = 32
PILOT_RESERVATION_GIB = 1
PILOT_REQUIRED_FREE_BYTES = (PILOT_RESERVE_GIB + PILOT_RESERVATION_GIB) * 1024 ** 3

# ACTUAL shared PX worker boundary. A pilot-private lock or lease root cannot
# exclude a live PX arm: cross-campaign exclusion requires the real
# ``.global-worker.lock`` and the same durable lease journal the independent
# watchdog supervises. The graphroot comes from PX's own pinned storage.conf so
# readiness is bound to the same store namespace. All of these are proven by
# ``verify_shared_px_boundary`` before any admission; never assumed.
SHARED_PX_BOUNDARY = {
    "worker_root": "/workspace/ivanka-exploratory-ten-20261121",
    "global_lock": "/workspace/ivanka-exploratory-ten-20261121/.global-worker.lock",
    "lease_root": "/workspace/ivanka-exploratory-ten-20261121",
    "lease_journal": "/workspace/ivanka-exploratory-ten-20261121/.worker-lease.jsonl",
    "storage_conf": "/workspace/ivanka-exploratory-ten-20261121/storage.conf",
    "storage_conf_sha256": "fdf5ce294ebcd8a950d1ae2016032a2620e9b16cabf33c772dc43ab425ecec21",
    "graphroot": "/workspace/ivanka-exploratory-podman-20261121/store",
    "watchdog_alive": "/workspace/ivanka-exploratory-ten-20261121/.watchdog-alive.json",
}
PX_ROOT = Path(SHARED_PX_BOUNDARY["worker_root"])

PILOT_ROOT = Path("/workspace/ivanka-p1-pilot-950fe331-20261126")
# Exclusion primitives are SHARED with PX; only the STOP sentinel stays
# owner-bound (it is a boundary request, not an exclusion primitive).
DEFAULT_LOCK = SHARED_PX_BOUNDARY["global_lock"]
DEFAULT_LEASE_ROOT = SHARED_PX_BOUNDARY["lease_root"]
DEFAULT_STOP = str(PILOT_ROOT / "p1-prospective.STOP")
DEFAULT_STORAGE_CONF = SHARED_PX_BOUNDARY["storage_conf"]
DEFAULT_EVIDENCE_ROOT = str(PILOT_ROOT / "evidence")
SLOT_AUTH_PATH = PILOT_ROOT / "operator-slot.json"
PENDING_SLOT = "NO-SLOT-GRANTED"


def load_pinned_json(path, expected_sha, *, label):
    """Read a durable pin-verified JSON manifest (never a symlink)."""
    target = Path(path)
    if target.is_symlink() or not target.is_file():
        raise ValueError(f"{label}: manifest missing or symlink")
    actual = sha256(target)
    if actual != expected_sha:
        raise ValueError(f"{label}: pin mismatch {actual} != {expected_sha}")
    return json.loads(target.read_text()), actual


def load_case_manifest():
    return load_pinned_json(CASES_MANIFEST, PINS_V2["cases_manifest"],
                            label="cases")


def load_image_manifest():
    return load_pinned_json(IMAGE_MANIFEST, PINS_V2["image_manifest"],
                            label="image")


def explicit_cases(cases_manifest):
    """Exactly four residual + two control synthetic cases, no full464."""
    residual = tuple(cases_manifest["residual_cases"])
    control = tuple(cases_manifest["control_cases"])
    if len(residual) != 4 or len(control) != 2:
        raise ValueError("pilot case design must be 4 residual + 2 control")
    if set(residual) & set(control):
        raise ValueError("residual and control case sets overlap")
    return residual + control


def verify_px_store_binding(storage_conf, *, expected_graphroot=None,
                            expected_sha=None):
    """Derive the graphroot from the pinned PX storage.conf, fail closed.

    The watchdog ALIVE record must name this exact graphroot. Passing an
    operator-supplied string would allow a ready record from a different store
    to unblock admission; deriving it from the pinned config makes the binding
    match by construction. No Podman command is run in this read-only helper.
    """
    conf = Path(storage_conf)
    if conf.is_symlink() or not conf.is_file():
        raise ValueError("pinned PX storage.conf missing or symlink")
    digest = sha256(conf)
    if digest != (expected_sha or PINS_V2["storage_conf"]):
        raise ValueError("pinned PX storage.conf hash differs")
    try:
        data = tomllib.loads(conf.read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError("pinned PX storage.conf is not valid TOML") from exc
    if not isinstance(data, dict) or not isinstance(data.get("storage"), dict):
        raise ValueError("pinned PX storage.conf lacks [storage]")
    graphroot = data["storage"].get("graphroot")
    if not isinstance(graphroot, str) or not graphroot:
        raise ValueError("pinned PX storage.conf lacks graphroot")
    if expected_graphroot is not None and graphroot != str(expected_graphroot):
        raise ValueError("watchdog graphroot does not match pinned PX store")
    return {"storage_conf": str(conf), "storage_conf_sha256": digest,
            "graphroot": graphroot}


def verify_shared_px_boundary(*, lock, lease_root, watchdog_path,
                              storage_conf, graphroot, expected=None):
    """Fail closed unless the pilot is inside the ACTUAL shared PX boundary.

    A pilot-private ``pilot.lock`` or a private lease journal cannot exclude a
    live PX arm. Exclusion is only real when both campaigns contend for the
    same ``.global-worker.lock`` and write leases to the same durable journal
    that the independent watchdog discovers and supervises. Readiness must be
    bound to that watchdog's graphroot. This proof is read-only: it never
    acquires a lock, writes a lease, creates a STOP or touches a container.
    """
    exp = dict(expected or SHARED_PX_BOUNDARY)

    def _resolve(value, label):
        path = Path(value)
        if path.is_symlink():
            raise ValueError(f"shared PX {label} is a symlink")
        return path.resolve()

    lock_path = _resolve(lock, "global worker lock")
    if lock_path != Path(exp["global_lock"]).resolve():
        raise ValueError("lock is not the actual PX .global-worker.lock; "
                         "a pilot-private lock cannot exclude PX")
    if not lock_path.is_file():
        raise ValueError("actual PX global-worker lock is missing")

    lease_path = _resolve(lease_root, "lease root")
    if lease_path != Path(exp["lease_root"]).resolve():
        raise ValueError("lease root is not the shared PX worker root")
    if not lease_path.is_dir():
        raise ValueError("shared PX lease root is missing")

    journal = _resolve(Path(lease_root) / ".worker-lease.jsonl", "lease journal")
    if journal != Path(exp["lease_journal"]).resolve():
        raise ValueError("lease journal is not the PX durable lease journal")
    if not journal.is_file():
        raise ValueError("shared PX durable lease journal is missing")

    conf = _resolve(storage_conf, "storage.conf")
    if conf != Path(exp["storage_conf"]).resolve():
        raise ValueError("storage.conf is not the actual PX storage.conf")
    if not conf.is_file():
        raise ValueError("actual PX storage.conf is missing")
    if sha256(conf) != exp["storage_conf_sha256"]:
        raise ValueError("PX storage.conf pin differs")

    if str(graphroot) != str(exp["graphroot"]):
        raise ValueError("graphroot differs from the PX watchdog graphroot; "
                         "readiness would bind to a foreign store")

    alive = _resolve(watchdog_path, "watchdog readiness record")
    if alive != Path(exp["watchdog_alive"]).resolve():
        raise ValueError("watchdog readiness record is not the shared PX ALIVE record")

    return {
        "shared": True,
        "global_lock": str(lock_path),
        "lease_root": str(lease_path),
        "lease_journal": str(journal),
        "storage_conf": str(conf),
        "storage_conf_sha256": exp["storage_conf_sha256"],
        "graphroot": str(graphroot),
        "watchdog_alive": str(alive),
        "watchdog_alive_present": alive.is_file(),
        "kernel_enforcement": False,
    }


def _default_inspect(image, fmt):
    """Read-only Podman inspect; never run, import, tag or delete an image."""
    result = subprocess.run(
        ["podman", "image", "inspect", "--format", fmt, image],
        capture_output=True, text=True, timeout=60, check=False)
    return result.returncode, result.stdout.strip()


def verify_image_contract(image, commit, *, env=None, inspect=None,
                          image_manifest=None):
    """Bind image to source, binary and frozen parent without building it."""
    manifest = image_manifest or load_image_manifest()[0]
    if (len(image) != 64 or any(c not in "0123456789abcdef" for c in image)):
        raise ValueError("candidate image must be a full immutable SHA-256")
    if image == PARENT_IMAGE:
        raise ValueError("frozen baseline image may not be rerun as candidate")
    if commit != manifest["candidate_source_commit"]:
        raise ValueError("candidate source commit differs from pinned image manifest")
    run_inspect = inspect or _default_inspect
    rc, identity = run_inspect(image, "{{.Id}}")
    if rc != 0 or identity.removeprefix("sha256:") != image:
        raise ValueError("candidate image identity differs from its digest")
    rc, raw_labels = run_inspect(image, "{{json .Config.Labels}}")
    if rc != 0:
        raise ValueError("candidate image labels unreadable")
    labels = json.loads(raw_labels)
    for key, value in manifest["expected_labels"].items():
        if labels.get(key) != value:
            raise ValueError(f"candidate image label {key} differs from pin")
    rc, child = run_inspect(image, "{{json .RootFS.Layers}}")
    rc_parent, parent = run_inspect(PARENT_IMAGE, "{{json .RootFS.Layers}}")
    if rc != 0 or rc_parent != 0:
        raise ValueError("image layer inspection unavailable")
    child_layers = json.loads(child)
    parent_layers = json.loads(parent)
    if child_layers[:-1] != parent_layers or len(child_layers) != len(parent_layers) + 1:
        raise ValueError("candidate is not a one-layer binary-only overlay")
    return {"labels": labels, "parent": PARENT_IMAGE,
            "layer_contract": manifest["layer_contract"]}


def verify_operator_slot(slot, *, path=SLOT_AUTH_PATH, wall=None):
    """Require the operator's exact, currently-valid slot token."""
    if not isinstance(slot, str) or not slot or slot == PENDING_SLOT:
        raise ValueError("no operator slot granted")
    target = Path(path)
    if target.is_symlink() or not target.is_file():
        raise ValueError("operator slot authorization missing")
    record = json.loads(target.read_text())
    if record.get("schema") != "ivanka.p1.operator-slot.v1":
        raise ValueError("unknown operator slot schema")
    if record.get("slot") != slot:
        raise ValueError("operator slot differs from granted slot")
    expiry = record.get("expires_utc")
    if (not isinstance(expiry, (int, float)) or not math.isfinite(expiry)
            or (wall or time.time)() > expiry):
        raise ValueError("operator slot expired")
    return record


def check_own_stop(stop_path, owner):
    """Read-only owner check; does not create or retire the STOP sentinel."""
    target = Path(stop_path)
    if target.is_symlink() or not target.is_file():
        return False
    return target.read_text().strip() == str(owner)


def build_command(case_dir, output_dir, image, timer, container_name, cidfile):
    """Exact integrated MiCall command with a harness-pinned cidfile."""
    return [
        "podman", "run", "--pull=never", "--network=none",
        "--userns=host", "--cpus=2", "--memory=" + str(MEMORY_BYTES),
        "--name", container_name, "--cidfile", str(cidfile),
        "--timeout", str(PODMAN_TIMEOUT_SECONDS), "--stop-timeout", "2",
        "-v", str(Path(case_dir) / "reads") + ":/reads:ro",
        "-v", str(Path(output_dir)) + ":/results:rw",
        "-v", str(Path(timer)) + ":/ivanka-timer.py:ro",
        "--entrypoint", "/opt/venv/bin/python", image,
        "/ivanka-timer.py", "/results/timing.json",
        "micall", "analyze", "sample",
        "/reads/R1.fastq.gz", "/reads/R2.fastq.gz", "/results",
        "--denovo", "--keep_scratch", "--bad_cycles_csv",
        "/results/bad_cycles.csv", "--all_projects",
    ]


def wait_for_cidfile(cidfile, process, timeout=60, clock=time.monotonic,
                     sleep=time.sleep):
    """Block until Podman has written a valid CID or the spawn has failed."""
    deadline = clock() + timeout
    path = Path(cidfile)
    while clock() < deadline:
        if path.is_file() and not path.is_symlink():
            text = path.read_text().strip()
            if len(text) == 64 and all(c in "0123456789abcdef" for c in text):
                return text
        if process.poll() is not None:
            if path.is_file() and not path.is_symlink():
                text = path.read_text().strip()
                if len(text) == 64 and all(c in "0123456789abcdef" for c in text):
                    return text
            raise RuntimeError("podman exited before cidfile was written")
        sleep(0.2)
    raise RuntimeError("cidfile was not written before spawn timeout")


class CaseExecution:
    """Mutable per-case holder shared by spawn/running/measure closures."""

    def __init__(self, command, env, log_path):
        self.command = list(command)
        self.env = dict(env)
        self.log_path = Path(log_path)
        self.process = None
        self.started = None
        self.log_handle = None

    def spawn(self, cidfile, env, timeout=60):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_handle = self.log_path.open("wb")
        self.process = subprocess.Popen(
            self.command, env=self.env, stdout=self.log_handle,
            stderr=subprocess.STDOUT)
        self.started = time.monotonic()
        wait_for_cidfile(cidfile, self.process, timeout=timeout)
        return self.process

    def running(self):
        return self.process is not None and self.process.poll() is None

    def measure(self):
        # watch_bound samples tree RSS from the exact bound CID.
        return True

    def close(self):
        if self.process is not None and self.process.poll() is None:
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.log_handle is not None:
            self.log_handle.close()
            self.log_handle = None


def _prepare_case_dir(destination):
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(f"case directory already exists: {destination}")
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "bad_cycles.csv").write_text("tile,cycle\n")
    return destination


def stage_physical_canary(destination, spec):
    """Stage attested physical reads into the same reference-blind contract."""
    r042 = spec["r042"]
    target = _prepare_case_dir(destination)
    (target / "reads").mkdir()
    staged = {}
    for key, name in (("r1_sha256", "R1.fastq.gz"), ("r2_sha256", "R2.fastq.gz")):
        source = Path(r042["reads_dir"]) / r042["r1" if name.startswith("R1") else "r2"]
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"physical canary read missing: {source}")
        if sha256(source) != r042[key]:
            raise ValueError(f"physical canary read pin differs: {source}")
        link = target / "reads" / name
        try:
            os.link(source, link)
        except OSError:
            link.write_bytes(source.read_bytes())
        staged["reads/" + name] = r042[key]
    manifest = {
        "schema": "ivanka.p1.physical-canary-case.v1",
        "id": "physical-canary-R042",
        "family": "physical",
        "hidden_truth_file": None,
        "score_model_revision": 2,
        "sha256": staged,
    }
    (target / "manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n")
    return target, staged


def score_case(case_dir, destination, record, image):
    """Post-hoc scoring only: hidden truth never enters the container argv."""
    manifest_data = json.loads((Path(case_dir) / "manifest.json").read_text())
    clock = json.loads((Path(destination) / "timing.json").read_text())
    if (clock.get("timing_origin") != TIMING_ORIGIN
            or clock.get("exit_code") != 0
            or not isinstance(clock.get("seconds"), (int, float))
            or not math.isfinite(clock["seconds"]) or clock["seconds"] <= 0):
        raise ValueError("invalid in-container timing")
    metrics = evaluate_final_alignment(
        manifest_data,
        Path(case_dir) / "hidden-truth/haplotypes.fasta",
        Path(destination))
    if metrics["score_origin"] != MULTITRUTH_SCORE_ORIGIN:
        raise ValueError("wrong final MiCall score origin")
    record.update(
        status="success", seconds=clock["seconds"], timing=clock,
        score=metrics["score"], dominant_exact=metrics["dominant_exact"],
        final_dominant=metrics["source"], per_truth=metrics["source"]["per_truth"],
        sha256=image,
    )
    return record


def _physical_result(destination, record, image):
    """Physical canary: attest timing + output hashes, never score with truth."""
    clock = json.loads((Path(destination) / "timing.json").read_text())
    if (clock.get("timing_origin") != TIMING_ORIGIN
            or clock.get("exit_code") != 0
            or not isinstance(clock.get("seconds"), (int, float))
            or not math.isfinite(clock["seconds"]) or clock["seconds"] <= 0):
        raise ValueError("invalid in-container timing")
    outputs = {}
    for path in sorted(Path(destination).glob("outcome*.json")):
        outputs[path.name] = sha256(path)
    record.update(status="success", seconds=clock["seconds"], timing=clock,
                  output_sha256=outputs, score=None, sha256=image,
                  truth_used_at_assembly_time=False)
    return record


def run_case(*, case_id, role, case_dir, destination, image, commit, timer,
             env, owner, lock_path, stop_path, lease_root, disk_path,
             watchdog_path, watchdog_graphroot, case_hashes=None,
             watchdog_ready=None, watchdog_snapshot=None, disk_usage=None,
             limit=MEMORY_BYTES, wall_seconds=WALL_CAP_SECONDS,
             deadline_utc=None, snapshot=None, clock=None, sleep=None,
             audit=None, bind_container=None, stop_cid_fn=None,
             spawn_timeout=60, physical=False):
    """Run one bounded case under the shared guard's real-heartbeat lifecycle."""
    case_dir = Path(case_dir)
    destination = Path(destination)
    manifest_data = json.loads((case_dir / "manifest.json").read_text())
    expected_hashes = case_hashes or manifest_data["sha256"]
    if manifest_data.get("sha256") != expected_hashes:
        raise ValueError("case manifest hash differs from frozen cohort")
    if manifest_data.get("score_model_revision") != 2:
        raise ValueError("case manifest differs from expected provenance")
    if not physical and manifest_data.get("hidden_truth_file") != (
            "hidden-truth/haplotypes.fasta"):
        raise ValueError("synthetic case hidden-truth provenance differs")
    hashes = verify_case_hashes(case_dir, expected_hashes)

    dest = _prepare_case_dir(destination)
    container_name = "ivanka-p1-pilot-" + hashlib.sha256(
        (case_id + ":" + image + ":" + str(dest)).encode()).hexdigest()[:18]
    cidfile_holder = {}

    def command_builder(cidfile):
        command = build_command(case_dir, dest, image, timer,
                                container_name, cidfile)
        assert_reference_blind(command)
        atomic_json(dest / "argv.json", command)
        return command

    execution = CaseExecution([], env, dest / "podman.log")

    def spawn(cidfile, spawn_env):
        cidfile_holder["path"] = cidfile
        command = command_builder(cidfile)
        execution.command = command
        execution.env = dict(spawn_env)
        execution.spawn(cidfile, spawn_env, timeout=spawn_timeout)

    # PR527 guard owns the real durable heartbeat (before_spawn / bound /
    # refresh). No caller-supplied heartbeat is passed or overridden here.
    guard_stop.arm(stop_path, owner)
    source_hashes = candidate_source_hashes(dest, hashes, image)

    record = {
        "status": "failed", "score": None,
        "score_origin": None if physical else MULTITRUTH_SCORE_ORIGIN,
        "timing_origin": TIMING_ORIGIN,
        "sha256": image, "container_name": container_name,
        "exit_code": None, "per_truth": {}, "diagnostics": {},
        "argv": None, "role": role,
        "truth_used_at_assembly_time": False,
    }

    guard_result = None
    try:
        guard_result = p1_harness.run_prospective(
            owner=owner, lease_root=lease_root, stop_path=stop_path,
            disk_path=disk_path, spawn=spawn, env=env, lock_path=lock_path,
            watchdog_ready=watchdog_ready, watchdog_path=watchdog_path,
            watchdog_graphroot=watchdog_graphroot,
            watchdog_snapshot=watchdog_snapshot,
            disk_reserve_bytes=PILOT_RESERVE_GIB * 1024 ** 3,
            disk_usage=disk_usage, limit=limit, wall_seconds=wall_seconds,
            deadline_utc=deadline_utc, running=execution.running,
            measure=execution.measure, snapshot=snapshot, clock=clock,
            sleep=sleep, audit=audit, bind_container=bind_container,
            stop_cid=stop_cid_fn)
        record["exit_code"] = (execution.process.returncode
                               if execution.process is not None else None)
        record["returncode"] = record["exit_code"]
        record["argv"] = execution.command
        guard_info = guard_result.get("result") or {}
        record["peak_sampled_rss_bytes"] = guard_info.get("peak_rss")
        record["rss_sample_scope"] = guard_info.get("rss_sample_scope")
        record["kernel_enforcement"] = guard_info.get("kernel_enforcement")
        record["teardown"] = guard_info.get("teardown")
        record["container_dead"] = True
        if physical:
            _physical_result(dest, record, image)
        else:
            score_case(case_dir, dest, record, image)
    except GuardExceeded as exc:
        record["error"] = exc.reason
        record["guard_error"] = exc.reason
        record["guard_teardown_error"] = exc.teardown_error
        record["guard_result"] = exc.guard_result
        if execution.process is not None:
            record["exit_code"] = execution.process.returncode
            record["returncode"] = execution.process.returncode
        record["argv"] = execution.command
        guard_result = {"status": "fail_closed", "reason": exc.reason,
                        "result": exc.guard_result, "teardown": exc.teardown}
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
        record["argv"] = execution.command
        guard_result = {"status": "error", "reason": record["error"],
                        "result": None}
    finally:
        execution.close()

    if record.get("status") == "success":
        try:
            verify_case_hashes(case_dir, hashes)
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = f"post_score_input_drift:{exc}"
            record["score"] = None

    source_hashes = candidate_source_hashes(
        dest, hashes, image,
        {"podman.log": sha256(dest / "podman.log")}
        if (dest / "podman.log").is_file() else None)
    record["source_hashes"] = source_hashes
    try:
        record["diagnostics"] = (
            {"physical_canary": True} if physical else _public_diagnostics(dest))
    except Exception as exc:
        record["diagnostics"] = {"error": f"{type(exc).__name__}: {exc}"}

    row = {
        "schema": "ivanka.p1.bounded-pilot-case.v2",
        "status": STATUS,
        "case_id": case_id,
        "role": role,
        "candidate_source_commit": commit,
        "candidate_image": image,
        "input_sha256": input_fingerprint(hashes),
        "case_hashes": hashes,
        "result": record,
        "guard": {
            "status": (guard_result or {}).get("status"),
            "lease": (guard_result or {}).get("lease"),
            "deadline_utc": (guard_result or {}).get("deadline_utc"),
            "stop_retired_by": (guard_result or {}).get("stop_retired_by"),
            "teardown": ((guard_result or {}).get("result") or {}).get(
                "teardown") or (guard_result or {}).get("teardown"),
            "peak_rss": ((guard_result or {}).get("result") or {}).get(
                "peak_rss"),
            "rss_sample_scope": ((guard_result or {}).get("result") or {}).get(
                "rss_sample_scope"),
            "kernel_enforcement": ((guard_result or {}).get("result") or {}).get(
                "kernel_enforcement"),
            "heartbeat": "guard_owned_real_emitter",
        },
    }
    atomic_json(dest / "case.json", row)
    return row


def _public_diagnostics(dest):
    from benchmarks.assembler_bench.sam_metrics import public_diagnostics
    return public_diagnostics(dest)


def prepare(args, *, image_inspect=None, image_manifest=None,
            store_conf=None, disk_usage_fn=None, wall=None):
    """Read-only gate evaluation and durable prepared manifest, no spawn."""
    cases_manifest, cases_sha = load_case_manifest()
    image_doc, image_sha = load_image_manifest()
    selected = explicit_cases(cases_manifest)
    requested = tuple(args.cases.split(",")) if args.cases else selected
    if not requested or len(set(requested)) != len(requested):
        raise ValueError("invalid or duplicate explicit case list")
    known = set(selected) | {cases_manifest["physical_canary"]["case_id"]}
    unknown = [case for case in requested if case not in known]
    if unknown:
        raise ValueError(f"unknown case(s): {', '.join(unknown)}")

    verify_pins(Path(args.data), Path(args.frozen_results), Path(args.timer))
    store = verify_px_store_binding(
        store_conf or args.storage_conf, expected_sha=PINS_V2["storage_conf"])
    shared = verify_shared_px_boundary(
        lock=args.lock, lease_root=args.lease_root,
        watchdog_path=args.watchdog_path,
        storage_conf=store_conf or args.storage_conf,
        graphroot=store["graphroot"])
    contract = verify_image_contract(
        args.image, args.commit, inspect=image_inspect,
        image_manifest=image_doc or image_manifest)

    free = (disk_usage_fn or _disk_free)(args.disk_path)
    if free < PILOT_REQUIRED_FREE_BYTES:
        raise ValueError(
            f"disk admission: {free} free < {PILOT_REQUIRED_FREE_BYTES} required")

    owner = args.owner or f"p1-pilot:{os.getpid()}"
    manifest = {
        "schema": SCHEMA,
        "status": STATUS,
        "qualified": False,
        "guard_status": "NO-GO pending independent reviewer approval and operator slot",
        "integration_base": INTEGRATION_BASE,
        "candidate_source_commit": SOURCE_COMMIT,
        "candidate_image": args.image,
        "candidate_image_contract": contract,
        "cases_manifest_sha256": cases_sha,
        "image_manifest_sha256": image_sha,
        "storage": store,
        "shared_px_boundary": shared,
        "watchdog": {
            "path": str(args.watchdog_path),
            "graphroot": store["graphroot"],
            "graphroot_source": "shared PX storage.conf (match by construction)",
        },
        "disk_admission": {
            "reserve_gib": PILOT_RESERVE_GIB,
            "reservation_gib": PILOT_RESERVATION_GIB,
            "required_free_bytes": PILOT_REQUIRED_FREE_BYTES,
            "observed_free_bytes": int(free),
        },
        "limits": {
            "wall_seconds": WALL_CAP_SECONDS,
            "memory_bytes": MEMORY_BYTES,
            "podman_timeout_seconds": PODMAN_TIMEOUT_SECONDS,
            "reserve_gib": RESERVE_GIB,
            "admission_gib": ADMISSION_GIB,
        },
        "paths": {
            "lock": str(args.lock), "stop": str(args.stop),
            "lease_root": str(args.lease_root), "disk_path": str(args.disk_path),
            "evidence_root": str(args.out), "slot_auth": str(SLOT_AUTH_PATH),
        },
        "owner": owner,
        "explicit_case_list": list(requested),
        "design": {
            "residual": list(cases_manifest["residual_cases"]),
            "control": list(cases_manifest["control_cases"]),
            "physical_canary": cases_manifest["physical_canary"]["case_id"],
        },
        "no_full464_rerun": True,
        "truth_used_at_assembly_time": False,
        "heartbeat": "shared guard real durable heartbeat (not caller injected)",
        "spawned": False,
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    atomic_json(out / "prepared_manifest.json", manifest)
    return manifest


def _disk_free(path):
    import shutil
    return shutil.disk_usage(str(path)).free


def verify_pins(data, frozen_path, timer):
    """Fail closed if any frozen input/score pin differs."""
    for path, pin in ((Path(data) / "cohort.json", PINS["cohort.json"]),
                      (Path(frozen_path), PINS["phase-synthetic464/results.jsonl"]),
                      (Path(timer), PINS["inside_container_timing.py"])):
        if sha256(path) != pin:
            raise ValueError(f"source hash gate failed for {path}")
    return True


def load_case_hashes(data, frozen_path):
    cohort = json.loads((Path(data) / "cohort.json").read_text())
    case_hashes = {entry["id"]: entry["sha256"] for entry in cohort["cases"]}
    frozen, frozen_hash = load_frozen(
        Path(frozen_path), PINS["phase-synthetic464/results.jsonl"], case_hashes)
    return case_hashes, frozen, frozen_hash


def run(args, *, env=None, image_inspect=None, image_manifest=None,
        store_conf=None, watchdog_ready=None, watchdog_snapshot=None,
        snapshot=None, clock=None, sleep=None, audit=None, disk_usage=None,
        disk_usage_fn=None, bind_container=None, stop_cid_fn=None,
        wall=None):
    manifest = prepare(args, image_inspect=image_inspect,
                       image_manifest=image_manifest, store_conf=store_conf,
                       disk_usage_fn=disk_usage_fn, wall=wall)
    out = Path(args.out)
    env = podman_env(args.storage_conf) if env is None else dict(env)
    summary = {
        "schema": SCHEMA, "status": STATUS, "qualified": False,
        "guard_status": manifest["guard_status"],
        "prepared_manifest_sha256": sha256(out / "prepared_manifest.json"),
        "spawned": False,
    }
    # Check-only is the default-preparation path: no STOP, no lease, no spawn.
    if args.check:
        atomic_json(out / "check_summary.json", summary)
        return summary

    slot = verify_operator_slot(args.slot, wall=wall)
    if not args.armed:
        raise ValueError("--armed required to spawn; source-only until slot granted")
    if not manifest.get("shared_px_boundary", {}).get("shared"):
        raise ValueError("shared PX worker boundary not proven at preparation")
    if (args.lock != SHARED_PX_BOUNDARY["global_lock"]
            or args.lease_root != SHARED_PX_BOUNDARY["lease_root"]):
        raise ValueError("execution must use the shared PX lock and lease root")
    if manifest["paths"]["stop"] != DEFAULT_STOP:
        raise ValueError("pilot must use its own owner-bound STOP")
    summary["slot"] = slot["slot"]

    case_hashes, _frozen, frozen_hash = load_case_hashes(args.data,
                                                          args.frozen_results)
    cases_doc, _cases_sha = load_case_manifest()
    role_by_id = {}
    for cid in cases_doc["residual_cases"]:
        role_by_id[cid] = "residual"
    for cid in cases_doc["control_cases"]:
        role_by_id[cid] = "control"
    canary = cases_doc["physical_canary"]
    role_by_id[canary["case_id"]] = "physical_canary"

    owner = manifest["owner"]
    results_path = out / "results.jsonl"
    completed = []
    for case_id in manifest["explicit_case_list"]:
        physical = case_id == canary["case_id"]
        if physical:
            spec, _ = load_pinned_json(
                canary["spec_path"], PINS_V2["physical_spec"], label="physical spec")
            case_dir, hashes = stage_physical_canary(out / case_id, spec)
        else:
            case_dir = Path(args.data) / case_id
            hashes = case_hashes[case_id]
            verify_case_hashes(case_dir, hashes)
        row = run_case(
            case_id=case_id, role=role_by_id[case_id], case_dir=case_dir,
            destination=out / case_id, image=args.image, commit=args.commit,
            timer=args.timer, env=env, owner=owner, lock_path=args.lock,
            stop_path=args.stop, lease_root=args.lease_root,
            disk_path=str(args.disk_path), watchdog_path=args.watchdog_path,
            watchdog_graphroot=manifest["storage"]["graphroot"],
            case_hashes=hashes, watchdog_ready=watchdog_ready,
            watchdog_snapshot=watchdog_snapshot, disk_usage=disk_usage,
            snapshot=snapshot, clock=clock, sleep=sleep, audit=audit,
            bind_container=bind_container, stop_cid_fn=stop_cid_fn,
            physical=physical)
        atomic_append(results_path, row)
        completed.append(row)
        print("P1_PILOT_CASE", case_id, role_by_id[case_id],
              row["result"]["status"], row["result"].get("error", ""), flush=True)
        if row["result"]["status"] != "success":
            break
        # Physical canary runs last, after a fresh 32+1 GiB disk admission.
        if physical:
            free = (disk_usage_fn or _disk_free)(args.disk_path)
            if free < PILOT_REQUIRED_FREE_BYTES:
                raise ValueError("post-canary disk admission shortfall")

    summary.update(
        spawned=True,
        cases_selected=list(manifest["explicit_case_list"]),
        cases_completed=[row["case_id"] for row in completed],
        cases_succeeded=[row["case_id"] for row in completed
                         if row["result"]["status"] == "success"],
        all_succeeded=all(row["result"]["status"] == "success"
                          for row in completed)
        and len(completed) == len(manifest["explicit_case_list"]),
        frozen_results_sha256=frozen_hash,
    )
    atomic_json(out / "summary.json", summary)
    print("P1_BOUNDED_PILOT", STATUS, "cases", len(completed),
          "all_succeeded", summary["all_succeeded"], flush=True)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(DEFAULT_DATA))
    parser.add_argument("--frozen-results", type=Path, default=Path(DEFAULT_FROZEN))
    parser.add_argument("--timer", type=Path, default=Path(DEFAULT_TIMER))
    parser.add_argument("--out", type=Path, default=Path(DEFAULT_EVIDENCE_ROOT))
    parser.add_argument("--image", default="PENDING_CANDIDATE_IMAGE_DIGEST")
    parser.add_argument("--commit", default=SOURCE_COMMIT)
    parser.add_argument("--storage-conf", type=Path, default=Path(DEFAULT_STORAGE_CONF))
    parser.add_argument("--lock", default=DEFAULT_LOCK)
    parser.add_argument("--stop", default=DEFAULT_STOP)
    parser.add_argument("--lease-root", default=DEFAULT_LEASE_ROOT)
    parser.add_argument("--disk-path", type=Path, default=Path("/workspace"))
    parser.add_argument("--watchdog-path", type=Path, required=True)
    parser.add_argument("--owner", default=None)
    parser.add_argument("--cases", help="comma-separated explicit case IDs")
    parser.add_argument("--check", action="store_true",
                        help="read-only preparation; no STOP, lease or spawn")
    parser.add_argument("--armed", action="store_true",
                        help="required together with an exact operator slot")
    parser.add_argument("--slot", default=PENDING_SLOT,
                        help="exact operator-granted slot token")
    args = parser.parse_args(argv)
    if not args.check and (not args.armed or args.slot == PENDING_SLOT):
        parser.error("execution requires --armed --slot <operator slot>; use --check to prepare")
    try:
        summary = run(args)
    except ValueError as exc:
        parser.error(f"gate failed closed: {exc}")
    return 0 if (args.check or summary["all_succeeded"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
