"""Source-only watchdog readiness / deployment probe for the real s6 layout.

Read-only by construction. This module NEVER arms a watchdog, installs or
starts an s6 service, writes an ALIVE record, acquires the PX worker lock,
writes a lease or STOP, invokes Podman, or touches a live arm. It only reads
the s6 scan directory, the service run script, the pinned watchdog code and the
watchdog ALIVE record, and returns a fail-closed readiness verdict.

Actual host layout (verified 2026-11-26, host marceline-dev):
  scan dir      /run/service
  service dirs  /run/s6/legacy-services/<name>
  activation    /run/service/<name> -> /run/s6/legacy-services/<name> symlink
  run file      <service dir>/run  (executable, exports pins inline; no env/ dir)
  status        <service dir>/supervise/status

The independent watchdog service is NOT deployed by this source. Deployment
and arming remain an explicit operator action at a natural PX boundary.
"""
from __future__ import annotations

import argparse
import json
import re
import stat
from pathlib import Path

from benchmarks.fail_closed_guard import heartbeat, identity, proc, startup, watchdog_contract
from benchmarks.fail_closed_guard.errors import GuardExceeded

from .p1_bounded_pilot_runner import SHARED_PX_BOUNDARY

S6_SCAN_DIR = "/run/service"
S6_SERVICE_DIR = "/run/s6/legacy-services"
SERVICE_NAME = "ivanka-watchdog"
WATCHDOG_MODULE = "fail_closed_guard.watchdog_cli"
WATCHDOG_CLI_REL = Path("benchmarks/fail_closed_guard/watchdog_cli.py")
# Exact reviewed CLI at PR527 b185c7f2 (the base of this pilot branch).
WATCHDOG_CLI_SHA256 = "e00b83adfbf8356f2f92ce92ecd2226854a182d21a21e24ca87d35ed205b5369"
REQUIRED_EXPORTS = ("WATCHDOG_ROOT", "WATCHDOG_CODE",
                    "WATCHDOG_STORAGE_CONF", "WATCHDOG_GRAPHROOT")
SCHEMA = "ivanka.p1.watchdog-readiness.v1"


def default_expected():
    """Expected pins derived from the shared PX worker boundary."""
    return {
        "WATCHDOG_ROOT": SHARED_PX_BOUNDARY["worker_root"],
        # Deployed 18:18Z at /workspace/ivanka-oci-transfer-20261126 (CLI sha pinned below).
        "WATCHDOG_CODE": "/workspace/ivanka-oci-transfer-20261126",
        "WATCHDOG_STORAGE_CONF": SHARED_PX_BOUNDARY["storage_conf"],
        "WATCHDOG_GRAPHROOT": SHARED_PX_BOUNDARY["graphroot"],
        "watchdog_cli_sha256": WATCHDOG_CLI_SHA256,
        "armed": True,
    }


def parse_exports(run_text):
    """Read ``export NAME=value`` lines from an s6 run script (no execution)."""
    exports = {}
    pattern = re.compile(
        r"^\s*export\s+(WATCHDOG_[A-Z0-9_]+)\s*=\s*[\"']?([^\s\"'#]+)[\"']?",
        re.MULTILINE)
    for match in pattern.finditer(run_text):
        exports[match.group(1)] = match.group(2)
    return exports


def probe_service_layout(*, scan_dir=S6_SCAN_DIR, services_dir=S6_SERVICE_DIR,
                         service=SERVICE_NAME, expected=None):
    """Fail-closed structural + pin check of the deployed s6 watchdog service."""
    exp = dict(expected or default_expected())
    scan = Path(scan_dir)
    base = Path(services_dir)
    link = scan / service
    checks = {
        "activation_symlink": False,
        "service_dir": False,
        "run_executable": False,
        "watchdog_module": False,
        "pins_match": False,
        "code_cli_pinned": False,
        "supervise_status": False,
        "armed": False,
    }
    detail = {"service": str(link), "service_dir": str(base / service)}

    if not link.is_symlink():
        detail["reason"] = "s6 activation symlink missing"
        return {"ready": False, "checks": checks, "detail": detail}
    target = link.resolve()
    checks["activation_symlink"] = True
    if target.parent != base.resolve() or target.name != service:
        detail["reason"] = "activation symlink does not target the s6 service dir"
        return {"ready": False, "checks": checks, "detail": detail}
    if not target.is_dir():
        detail["reason"] = "s6 service target is not a directory"
        return {"ready": False, "checks": checks, "detail": detail}
    checks["service_dir"] = True
    detail["target"] = str(target)

    run = target / "run"
    if run.is_symlink() or not run.is_file():
        detail["reason"] = "s6 run file missing or symlink"
        return {"ready": False, "checks": checks, "detail": detail}
    if not (run.stat().st_mode & stat.S_IXUSR):
        detail["reason"] = "s6 run file is not executable"
        return {"ready": False, "checks": checks, "detail": detail}
    checks["run_executable"] = True

    text = run.read_text()
    checks["watchdog_module"] = ("-m " + WATCHDOG_MODULE) in text
    exports = parse_exports(text)
    detail["exports"] = {k: exports.get(k) for k in ("WATCHDOG_ROOT",
                                                      "WATCHDOG_CODE",
                                                      "WATCHDOG_STORAGE_CONF",
                                                      "WATCHDOG_GRAPHROOT",
                                                      "WATCHDOG_ARMED")}
    mismatches = [key for key in REQUIRED_EXPORTS
                  if exports.get(key) != str(exp.get(key))]
    checks["pins_match"] = not mismatches
    if mismatches:
        detail["pin_mismatches"] = mismatches
    checks["armed"] = exports.get("WATCHDOG_ARMED") == "1"

    code = exports.get("WATCHDOG_CODE")
    if code:
        cli = Path(code) / WATCHDOG_CLI_REL
        if (not cli.is_symlink() and cli.is_file()
                and _sha256(cli) == exp["watchdog_cli_sha256"]):
            checks["code_cli_pinned"] = True
            detail["watchdog_cli"] = str(cli)

    status = target / "supervise" / "status"
    checks["supervise_status"] = (status.is_file() and not status.is_symlink())

    return {"ready": all(checks.values()), "checks": checks, "detail": detail}


def _sha256(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def probe_alive(*, root, graphroot, wall=None, max_age=None, snapshot=None):
    """Read-only ALIVE check, including a LIVE PID fingerprint comparison.

    An ALIVE record is only textual evidence. The guard contract is given a
    live /proc snapshot so a stale/reused PID fails closed; additionally the
    immutable starttime/pid_ns pair and the recorded cmdline hash are compared
    against the live process table before readiness is claimed.
    """
    path = heartbeat.alive_path(Path(root))
    live_snapshot = snapshot or proc.snapshot
    try:
        readiness = watchdog_contract.require_watchdog_readiness(
            path, graphroot=graphroot, wall=wall, max_age=max_age,
            snapshot=live_snapshot)
        record = json.loads(path.read_text())
        pid = int(record["pid"])
        observed = live_snapshot().get(pid)
        if observed is None:
            raise GuardExceeded("watchdog_identity_mismatch")
        if (startup.stable_fingerprint(observed) != tuple(record["fingerprint"])
                or identity.fingerprint(observed)[2] != record.get("cmdline_sha")):
            raise GuardExceeded("watchdog_identity_mismatch")
    except GuardExceeded as exc:
        return {"ready": False, "reason": exc.reason,
                "path": str(path), "root": str(root)}
    return {"ready": True, "path": str(path), "root": str(root),
            "live_pid": pid, "live_fingerprint_verified": True,
            "readiness": readiness}


def probe(*, scan_dir=S6_SCAN_DIR, services_dir=S6_SERVICE_DIR,
          service=SERVICE_NAME, expected=None, wall=None, snapshot=None):
    """Combine s6 layout, pin and ALIVE probes into one fail-closed verdict."""
    exp = dict(expected or default_expected())
    layout = probe_service_layout(scan_dir=scan_dir, services_dir=services_dir,
                                  service=service, expected=exp)
    alive = probe_alive(root=exp["WATCHDOG_ROOT"],
                        graphroot=exp["WATCHDOG_GRAPHROOT"], wall=wall,
                        snapshot=snapshot)
    return {"schema": SCHEMA, "ready": bool(layout["ready"] and alive["ready"]),
            "service_layout": layout, "alive": alive,
            "armed": bool(layout["checks"].get("armed")),
            "kernel_enforcement": False}


def deployment_plan(*, expected=None):
    """Exact, source-only operator deployment steps for the real s6 layout."""
    exp = dict(expected or default_expected())
    svc = str(Path(S6_SERVICE_DIR) / SERVICE_NAME)
    return {
        "schema": "ivanka.p1.watchdog-deployment-plan.v1",
        "scan_dir": S6_SCAN_DIR,
        "service_dir": svc,
        "activation": "ln -s %s %s/%s" % (svc, S6_SCAN_DIR, SERVICE_NAME),
        "run_script": {
            "exports": {
                "WATCHDOG_ROOT": exp["WATCHDOG_ROOT"],
                "WATCHDOG_CODE": "%s (CLI sha256 %s)" % (exp["WATCHDOG_CODE"], exp["watchdog_cli_sha256"]),
                "WATCHDOG_STORAGE_CONF": exp["WATCHDOG_STORAGE_CONF"],
                "WATCHDOG_GRAPHROOT": exp["WATCHDOG_GRAPHROOT"],
                "WATCHDOG_ARMED": "0 until operator authorization at a natural PX boundary",
            },
            "exec": "python3 -m %s --root ... --storage-conf ... --graphroot ..." % WATCHDOG_MODULE,
        },
        "probe_command": "PYTHONPATH=.:benchmarks python3 -m expanded.p1_watchdog_readiness --check",
        "notes": [
            "The watchdog never holds the PX global worker lock; it only reads the shared lease journal.",
            "Do not install or arm until operator authorization at a natural PX boundary.",
            "This plan writes nothing; all steps are operator actions.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="read-only readiness probe (default)")
    parser.add_argument("--scan-dir", default=S6_SCAN_DIR)
    parser.add_argument("--services-dir", default=S6_SERVICE_DIR)
    parser.add_argument("--service", default=SERVICE_NAME)
    parser.add_argument("--deployment-plan", action="store_true",
                        help="print the exact source-only deployment plan")
    args = parser.parse_args(argv)
    if args.deployment_plan:
        print(json.dumps(deployment_plan(), sort_keys=True, indent=2))
        return 0
    verdict = probe(scan_dir=args.scan_dir, services_dir=args.services_dir,
                    service=args.service)
    print(json.dumps(verdict, sort_keys=True, indent=2, default=str))
    return 0 if verdict["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
