"""Read-only, fail-closed live attestation for the PR535 guard cutover.

This module never mutates services, files, leases, receipts or registry. It has
two deliberately different verdicts:

* ``pre_cutover`` proves an **idle boundary** is safe to switch pins: exact old
  runtime/persistent script pins, a live old-code watchdog with real s6/proc
  identity and readiness, no supervisor process, no active lease, unlocked
  global lock and no foreign STOP sentinel.
* ``post_cutover`` proves the **running expected service**: exact new
  runtime/persistent script pins, live new-code watchdog and supervisor with
  real s6/proc identity, canonical code root and module bytes, and watchdog
  readiness. An active lease is normal here, but a foreign STOP is not.

A mismatch in any checked fact is a blocker, never a warning. Source-byte
verification alone is not live attestation; both phases bind the actual s6
PID to a real /proc snapshot and to the watchdog ALIVE record.
"""
import os
import re
from pathlib import Path

from benchmarks.fail_closed_guard import errors as guard_errors
from benchmarks.fail_closed_guard import heartbeat, lease, proc, watchdog_contract

from . import px_guard_source as guard_source

OLD_HEAD = "091f56275ae823cb3291b81dbdf016fcf16c3ea0"
OLD_ROOT = "/workspace/ivanka-guard-pr536-staged-20261126"
NEW_ROOT = "/workspace/ivanka-guard-pr535-staged-20261127"

# The supervisor loads control code (px_execution, px_supervisor, retry and disk
# retry admission); the immutable guard root predates those modules. A correct
# post-cutover deployment therefore runs the watchdog from the guard root and
# the supervisor from the separately reviewed control checkout, each bound to
# its own exact module chain. The control HEAD is an exact reviewed commit, not
# a self-referential future commit.
CONTROL_ROOT = str(guard_source.CONTROL_ROOT)
CONTROL_HEAD = "c3798910cb1d884ddea33cd1d0f405d7e0c31e2b"
CONTROL_MODULES = dict(guard_source._read_control_identity()["sources"])
CONTROL_MODULES.update(guard_source.EXPECTED)

PROJECT_ROOT = Path("/workspace/ivanka-exploratory-ten-20261121")
GRAPHROOT = Path("/workspace/ivanka-exploratory-podman-20261121/store")
REGISTRY = PROJECT_ROOT / "private-frozen-ten-pilot-registry-20gib-20261124.json"
S6_ROOT = Path("/run/s6/legacy-services")

# Options the pinned watchdog run script may append in addition to the bound
# --root/--graphroot. Recognised by name so an unknown token cannot hide a
# second configuration source; the attestation binds the pinned values through
# the script pins, service env and ALIVE graphroot cross-check separately.
WATCHDOG_OPTION_NAMES = ("--storage-conf", "--stop", "--min-free", "--reserve",
                         "--rss-limit", "--wall-seconds", "--max-age")

# Reviewed bytes of the old live guard (14-file PR536 map). Kept as explicit
# evidence for the pre-cutover phase; it is never used to attest new code.
OLD_MODULES = {
    "benchmarks/assembler_bench/exploratory_space.py":
        "bffdc90b703475aeb68f31c2df4334cb36a8912ebaba806cd7baee4d2bc18943",
    "benchmarks/memory_guard/proc.py":
        "086ce9aca6d73703216e841d8e9b580cab6678e743f868d6e133a50ba0d69e72",
    "benchmarks/memory_guard/guard.py":
        "6e096ffb7cae5014595a6aaa889beb2ed7d05172588556adb6a82ffa23e32dbe",
    "benchmarks/memory_guard/signals.py":
        "b5a4dc351da3fc9144bcfad7a26059a849e9c5a58980c26e3c004ad817d88c53",
    "benchmarks/fail_closed_guard/proc.py":
        "e8b4c9ebe1a8a3a509466cf824873820df962577352457c879090fd795030b31",
    "benchmarks/fail_closed_guard/watchdog.py":
        "a67bac2672efb961408f2401163b49e12e01c07c6300ffb200519c1cc07a6d5e",
    "benchmarks/fail_closed_guard/watchdog_contract.py":
        "a2d198b35f0c756cce68f094bebdf79068ad1a585f1f5f061e4e9c2c74906365",
    "benchmarks/fail_closed_guard/binding.py":
        "1e764c6a358ddc3b58fe09aa0948d6309b00942936ac525d93ef17d19516e945",
    "benchmarks/fail_closed_guard/identity.py":
        "1feecc9e75e71c4bf54b2dbd960cc92886fa00cd9a564c7d220e90f4163aa973",
    "benchmarks/fail_closed_guard/startup.py":
        "80b07ce334fa99691ed0a89baf9aa803d4e67631be72c022188963f094ae7b6d",
    "benchmarks/fail_closed_guard/watchdog_cli.py":
        "e00b83adfbf8356f2f92ce92ecd2226854a182d21a21e24ca87d35ed205b5369",
    "benchmarks/fail_closed_guard/natural_exit.py":
        "f7f6028273a5d7775b8d4ca6139e9659ca475a0aa36a3d12b1a736e429202cd6",
    "benchmarks/fail_closed_guard/watch.py":
        "07356fc4b29e1e6bc5b11659048bc5437a70037a29dde197dd795540fd66da96",
    "benchmarks/assembler_bench/exploratory_runtime/monitor.py":
        "b0bbefa221ff092acf33021b0203f2b07a912c250fc0893e8fdd59dad642293c",
}

PHASES = {
    "pre_cutover": {
        "root": OLD_ROOT, "head": OLD_HEAD, "modules": OLD_MODULES,
        "watchdog": {"root": OLD_ROOT, "head": OLD_HEAD, "modules": OLD_MODULES},
        "control": {"root": OLD_ROOT, "head": OLD_HEAD, "modules": OLD_MODULES},
        "supervisor": "absent", "idle_required": True,
    },
    "post_cutover": {
        # Top-level keys describe the immutable watchdog guard for compatibility.
        "root": NEW_ROOT, "head": guard_source.DEPLOYED_HEAD,
        "modules": dict(guard_source.EXPECTED),
        "watchdog": {"root": NEW_ROOT, "head": guard_source.DEPLOYED_HEAD,
                     "modules": dict(guard_source.EXPECTED)},
        "control": {"root": CONTROL_ROOT, "head": CONTROL_HEAD,
                    "modules": dict(CONTROL_MODULES)},
        "supervisor": "running", "idle_required": False,
    },
}


def _block(blockers, reason):
    if reason not in blockers:
        blockers.append(reason)


def _read(path):
    try:
        return Path(path).read_text()
    except OSError:
        return None


def _s6_pid(service_dir):
    """Derive the live service PID from the s6 supervise status, read-only."""
    status = Path(service_dir) / "supervise" / "status"
    if not status.is_file():
        return None
    blob = status.read_bytes()
    if len(blob) < 32:
        return None
    return int.from_bytes(blob[24:32], "big")


def _proc(pid, proc_root):
    entry = Path(proc_root) / str(int(pid))
    if not entry.is_dir():
        return None
    try:
        raw = (entry / "cmdline").read_bytes()
        cmd = raw.replace(b"\0", b" ").decode(errors="replace").strip()
        argv = [part.decode(errors="replace") for part in raw.split(b"\0") if part]
        env = {}
        for item in (entry / "environ").read_bytes().split(b"\0"):
            if b"=" in item:
                key, value = item.split(b"=", 1)
                env[key.decode(errors="replace")] = value.decode(errors="replace")
        cwd = os.readlink(entry / "cwd")
    except OSError:
        return None
    return {"pid": int(pid), "cmdline": cmd, "argv": argv,
            "cwd": cwd, "environ": env}


def _flock_locked(path):
    import fcntl
    fd = os.open(path, os.O_RDWR)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def _pin_lines(variable, root, head):
    return (
        "export %s=%s" % (variable, root),
        'test "$(git -C "$%s" rev-parse HEAD)" = %s || exit 1' % (variable, head),
        'git -C "$%s" diff --quiet HEAD || exit 1' % variable,
    )


def _check_script(label, text, expected, variable, markers, checks, blockers):
    check = {"present": text is not None}
    if text is None:
        _block(blockers, "missing_script:" + label)
        checks[label] = check
        return
    pins = _pin_lines(variable, expected["root"], expected["head"])
    check["pins"] = {line: line in text for line in pins}
    if not all(check["pins"].values()):
        _block(blockers, "script_pin_mismatch:" + label)
    # Only the CODE variables are configuration sources; binding their exact
    # values and exact HEAD pins lets both the guard and control roots coexist.
    roots = set(re.findall(r"(?:WATCHDOG_CODE|PX_CODE)=(\S+)", text))
    heads = set(re.findall(r'rev-parse HEAD\)" = ([a-f0-9]{40})', text))
    check["roots"] = sorted(roots)
    check["heads"] = sorted(heads)
    if roots != {expected["root"]} or heads != {expected["head"]}:
        _block(blockers, "foreign_script_pin:" + label)
    check["markers"] = {marker: marker in text for marker in markers}
    if not all(check["markers"].values()):
        _block(blockers, "script_marker_missing:" + label)
    checks[label] = check


def _check_code_root(label, code, table, pid, expected, checks, blockers,
                     *, module_reader, head_reader, git_present):
    check = {}
    if code != expected["root"]:
        _block(blockers, "wrong_code_root:" + label)
    check["code_root"] = code
    code_path = Path(code) if code else None
    if code_path and code_path.is_dir():
        if not git_present(code_path):
            _block(blockers, "code_root_not_git_checkout:" + label)
        else:
            try:
                check["code_head"] = head_reader(code_path)
            except ValueError:
                check["code_head"] = None
            if check["code_head"] != expected["head"]:
                _block(blockers, "code_head_mismatch:" + label)
        drifted = []
        for name, digest in expected["modules"].items():
            if module_reader(code_path, name) != digest:
                drifted.append(name)
        check["drifted_modules"] = drifted
        if drifted:
            _block(blockers, "module_bytes_mismatch:" + label)
    else:
        _block(blockers, "code_root_missing:" + label)
    record = table.get(pid)
    if (not isinstance(record, dict) or not isinstance(record.get("starttime"), int)
            or not isinstance(record.get("pid_ns"), int)
            or record["starttime"] <= 0 or record["pid_ns"] <= 0):
        _block(blockers, "proc_snapshot_unavailable:" + label)
        check["snapshot_identity"] = None
    else:
        check["snapshot_identity"] = [record["starttime"], record["pid_ns"]]
    return check


def _check_argv(label, argv, *, module, values, flags, checks, blockers,
                allowed_options=(), allowed_flags=()):
    """Bind module, exact option values/flag counts and the whole argv grammar.

    Tokens before ``-m`` belong to the pinned s6 launcher and are not a
    configuration source. From ``-m`` onward every token must be the module, a
    known option with its value, or a known flag: an extra token cannot smuggle
    configuration past the value and count bindings.
    """
    check = {"argv": argv}
    ok = True
    module_count = argv.count("-m")
    module_index = argv.index("-m") if module_count == 1 else None
    actual_module = ((argv[module_index + 1:module_index + 2] or [None])[0]
                     if module_index is not None else None)
    if module_count != 1 or actual_module != module:
        _block(blockers, "module_argv_mismatch:" + label)
        ok = False
    for option, expected in values.items():
        count = argv.count(option)
        check[option] = {"count": count}
        if count != 1:
            _block(blockers, "option_count_mismatch:%s:%s" % (label, option))
            ok = False
            continue
        actual = argv[argv.index(option) + 1:argv.index(option) + 2]
        actual = actual[0] if actual else None
        check[option]["value"] = actual
        if actual != expected:
            _block(blockers, "option_value_mismatch:%s:%s" % (label, option))
            ok = False
    for flag in flags:
        count = argv.count(flag)
        check[flag] = count
        if count != 1:
            _block(blockers, "flag_count_mismatch:%s:%s" % (label, flag))
            ok = False

    options = set(values) | set(allowed_options)
    known_flags = set(flags) | set(allowed_flags)
    tail = argv[module_index:] if module_index is not None else []
    unexpected = []
    index = 0
    while index < len(tail):
        token = tail[index]
        if token == "-m" or token == module:
            index += 1
        elif token in options:
            if index + 1 >= len(tail) or tail[index + 1].startswith("-"):
                _block(blockers, "option_value_missing:%s:%s" % (label, token))
                ok = False
                index += 1
            else:
                index += 2
        elif token in known_flags:
            index += 1
        else:
            unexpected.append(token)
            index += 1
    if unexpected:
        _block(blockers, "unexpected_argv_token:%s:%s" % (label, ",".join(unexpected)))
        ok = False
    check["unexpected_tokens"] = unexpected
    checks[label + "_argv_values"] = check
    return ok


def _check_env(label, env, expected_env, checks, blockers):
    check = {}
    ok = True
    for key, expected in expected_env.items():
        actual = env.get(key)
        check[key] = actual
        if actual != expected:
            _block(blockers, "env_mismatch:%s:%s" % (label, key))
            ok = False
    checks[label + "_env"] = check
    return ok


def _check_service(label, *, service, expected, presence, variable, module,
                   values, flags, env_expected, proc_root, s6_root, table,
                   checks, blockers, module_reader, head_reader, git_present,
                   allowed_options=(), allowed_flags=()):
    s6_pid = _s6_pid(Path(s6_root) / service)
    check = {"s6_pid": s6_pid}
    if presence == "absent":
        supervisor_argv = [pid for pid in table
                           if "-m assembler_bench.px_execution" in (
                               (_proc(pid, proc_root) or {}).get("cmdline", ""))
                           and "--supervise" in (
                               (_proc(pid, proc_root) or {}).get("cmdline", ""))]
        check["supervisor_processes"] = supervisor_argv
        if s6_pid or supervisor_argv:
            _block(blockers, "supervisor_not_idle:" + label)
        checks[label] = check
        return None, None
    if not s6_pid:
        _block(blockers, "s6_service_down:" + label)
        checks[label] = check
        return None, None
    proc = _proc(s6_pid, proc_root)
    check["proc"] = proc is not None
    if proc is None:
        _block(blockers, "proc_missing:" + label)
        checks[label] = check
        return None, None
    code = proc["environ"].get(variable)
    check["pythonpath_head"] = proc["environ"].get("PYTHONPATH", "").split(":")[0]
    if proc["environ"].get("PYTHONPATH", "").split(":")[0] != expected["root"]:
        _block(blockers, "pythonpath_mismatch:" + label)
    check["cmdline"] = proc["cmdline"]
    _check_argv(label, proc["argv"], module=module, values=values, flags=flags,
                checks=checks, blockers=blockers,
                allowed_options=allowed_options, allowed_flags=allowed_flags)
    _check_env(label, proc["environ"], env_expected, checks, blockers)
    check.update(_check_code_root(label, code, table, s6_pid, expected,
                                  checks, blockers, module_reader=module_reader,
                                  head_reader=head_reader, git_present=git_present))
    checks[label] = check
    return s6_pid, _proc(s6_pid, proc_root)


def attest(*, phase, project_root=PROJECT_ROOT, s6_root=S6_ROOT,
           proc_root="/proc", persistent_watchdog="/etc/services.d/ivanka-watchdog/run",
           runtime_watchdog=None, persistent_supervisor="/etc/services.d/px-cohort-supervisor/run",
           runtime_supervisor=None, global_lock=None, worker_journal=None,
           registry=REGISTRY, snapshot=None, lock_probe=None, now=None,
           module_reader=None,
           head_reader=None, git_present=None):
    """Return a read-only, fail-closed verdict for one exact cutover phase."""
    if phase not in PHASES:
        raise ValueError("unknown attestation phase: " + str(phase))
    expected = PHASES[phase]
    root = Path(project_root)
    s6_root = Path(s6_root)
    runtime_watchdog = runtime_watchdog or str(s6_root / "ivanka-watchdog" / "run")
    runtime_supervisor = runtime_supervisor or str(s6_root / "px-cohort-supervisor" / "run")
    global_lock = Path(global_lock or root / ".global-worker.lock")
    worker_journal = Path(worker_journal or root / lease.JOURNAL_NAME)
    if worker_journal.name != lease.JOURNAL_NAME:
        raise ValueError("worker journal must be the canonical lease journal")
    take_snapshot = snapshot or proc.snapshot
    table = take_snapshot()
    module_reader = module_reader or (
        lambda base, name: guard_source.digest(base / name)
        if not (base / name).is_symlink() and (base / name).is_file() else None)
    head_reader = head_reader or guard_source._git_head
    git_present = git_present or (lambda path: (path / ".git").exists())
    clock = now or (lambda: __import__("time").time())
    blockers = []
    registry = Path(registry)
    checks = {"phase": phase, "expected_root": expected["root"],
              "expected_head": expected["head"],
              "expected_watchdog_root": expected["watchdog"]["root"],
              "expected_control_root": expected["control"]["root"],
              "expected_control_head": expected["control"]["head"],
              "expected_registry": str(registry)}

    wd_persist = _read(persistent_watchdog)
    wd_runtime = _read(runtime_watchdog)
    sup_persist = _read(persistent_supervisor)
    sup_runtime = _read(runtime_supervisor)
    wd_markers = ("export WATCHDOG_ROOT=", "export WATCHDOG_STORAGE_CONF=",
                  "export WATCHDOG_GRAPHROOT=", "export WATCHDOG_STOP=",
                  "export WATCHDOG_ARMED=1", "-m fail_closed_guard.watchdog_cli",
                  'exec env PYTHONPATH="$CODE:$CODE/benchmarks"')
    sup_markers = ("export PX_ROOT=", "export PX_REGISTRY=",
                   'exec /bin/sh "$PX_CODE/scripts/px_cohort_s6_service.sh"',
                   "export WATCHDOG_ARMED=1")
    _check_script("persistent_watchdog", wd_persist, expected["watchdog"],
                  "WATCHDOG_CODE", wd_markers, checks, blockers)
    _check_script("runtime_watchdog", wd_runtime, expected["watchdog"],
                  "WATCHDOG_CODE", wd_markers, checks, blockers)
    _check_script("persistent_supervisor", sup_persist, expected["control"],
                  "PX_CODE", sup_markers, checks, blockers)
    _check_script("runtime_supervisor", sup_runtime, expected["control"],
                  "PX_CODE", sup_markers, checks, blockers)
    for label, text in (("persistent_supervisor", sup_persist),
                        ("runtime_supervisor", sup_runtime)):
        found = re.search(r"export PX_REGISTRY=(\S+)", text or "")
        actual = found.group(1) if found else None
        checks[label + "_registry_pin"] = actual
        if actual != str(registry):
            _block(blockers, "foreign_registry_pin:" + label)
    for label, a, b in (("watchdog", wd_persist, wd_runtime),
                        ("supervisor", sup_persist, sup_runtime)):
        if a is not None and b is not None and a != b:
            _block(blockers, "runtime_persist_mismatch:" + label)
        checks[label + "_scripts_identical"] = (a is not None and a == b)

    graphroot = GRAPHROOT
    if wd_persist:
        found = re.search(r"export WATCHDOG_GRAPHROOT=(\S+)", wd_persist)
        if found:
            graphroot = Path(found.group(1))
        if str(graphroot) != str(GRAPHROOT):
            _block(blockers, "foreign_graphroot")

    watchdog_pid, _ = _check_service(
        "watchdog", service="ivanka-watchdog", expected=expected["watchdog"],
        presence="running", variable="WATCHDOG_CODE",
        module="fail_closed_guard.watchdog_cli",
        values={"--root": str(root), "--graphroot": str(graphroot)}, flags=(),
        allowed_options=WATCHDOG_OPTION_NAMES,
        env_expected={"WATCHDOG_ROOT": str(root),
                      "WATCHDOG_GRAPHROOT": str(graphroot)},
        proc_root=proc_root, s6_root=s6_root, table=table,
        checks=checks, blockers=blockers, module_reader=module_reader,
        head_reader=head_reader, git_present=git_present)
    _check_service(
        "supervisor", service="px-cohort-supervisor", expected=expected["control"],
        presence=expected["supervisor"], variable="PX_CODE",
        module="assembler_bench.px_execution",
        values={"--registry": str(registry), "--root": str(root)},
        flags=("--supervise", "--armed"),
        env_expected={"PX_ROOT": str(root), "PX_REGISTRY": str(registry)},
        proc_root=proc_root, s6_root=s6_root, table=table,
        checks=checks, blockers=blockers, module_reader=module_reader,
        head_reader=head_reader, git_present=git_present)

    alive_path = heartbeat.alive_path(root)
    if watchdog_pid is None:
        _block(blockers, "watchdog_not_running")
    else:
        try:
            table_snapshot = lambda: table
            alive = heartbeat.read_alive(root, wall=clock, snapshot=table_snapshot)
            ready = watchdog_contract.require_watchdog_readiness(
                alive_path, graphroot=str(graphroot), wall=clock,
                snapshot=table_snapshot)
            checks["watchdog_readiness"] = ready
            record = table.get(watchdog_pid, {})
            if alive.get("pid") != watchdog_pid or tuple(
                    alive.get("fingerprint") or ()) != (
                    record.get("starttime"), record.get("pid_ns")):
                _block(blockers, "watchdog_alive_identity_mismatch")
        except (guard_errors.GuardExceeded, ValueError) as exc:
            checks["watchdog_readiness"] = {"error": str(exc)}
            _block(blockers, "watchdog_readiness_failed")

    try:
        events = lease.events(worker_journal.parent)
        latest = lease.latest(events)
        active = {name: row for name, row in latest.items()
                  if row.get("state") not in lease.CLOSED}
        checks["leases"] = {"events": len(events),
                            "latest_count": len(latest),
                            "active": sorted(active)}
        if expected["idle_required"] and active:
            _block(blockers, "active_lease")
    except (guard_errors.GuardExceeded, ValueError, TypeError) as exc:
        checks["leases"] = {"error": str(exc)}
        _block(blockers, "lease_journal_unreadable")

    probe = lock_probe or _flock_locked
    locked = probe(global_lock) if global_lock.exists() else None
    checks["global_lock"] = {"path": str(global_lock), "exists": global_lock.exists(),
                             "locked": locked}
    if expected["idle_required"] and locked:
        _block(blockers, "global_lock_busy")
    if not expected["idle_required"] and not global_lock.exists():
        _block(blockers, "global_lock_missing")

    sentinels = []
    stop = root / "STOP"
    if stop.exists() or stop.is_symlink():
        sentinels.append(stop.name)
    for item in root.glob("STOP*"):
        if item.name.startswith("STOP.resolved-"):
            continue
        sentinels.append(item.name)
    checks["stop_sentinels"] = sorted(set(sentinels))
    if sentinels:
        _block(blockers, "foreign_stop")

    ready = not blockers
    return {
        "kind": "px.live.attestation.v2",
        "phase": phase,
        "ready": ready,
        "blockers": blockers,
        "checks": checks,
        "attests_live_process_identity": ready and watchdog_pid is not None
        and expected["supervisor"] == "running",
        "kernel_enforcement": False,
    }
