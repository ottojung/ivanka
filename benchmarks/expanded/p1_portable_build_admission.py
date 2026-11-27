"""Source-only preflight for the guarded COPY-only portable 950fe331 build.

This prepares the exact plan / postbuild-receipt artifacts required by the
merged PR531 controller and PR535 copy-overlay admission. It never builds an
image, starts a container, touches the shared lease/watchdog, runs a case, or
invokes the live pilot controller. Mutating subcommands write ONLY inside the
caller's own evidence namespace and require an explicit --operator-confirm
owner string; that string is a labelling requirement, NOT an authorization to
build or arm.
"""
import argparse
import json
import os
import shlex
import shutil
import sys
from pathlib import Path

from expanded import p1_bounded_pilot_runner as runner
from fail_closed_guard import copy_overlay

SCHEMA = "ivanka.p1.portable-build-admission.v1"
OPERATOR_DISK_FLOOR = 35 * 1024 ** 3  # operator 2026-11-27 07:23Z directive
GUARD_RESERVE = 1 * 1024 ** 3
TAG_PREFIX = "ivanka-copy-"  # copy_overlay.TAG regex
DEFAULT_CODE_ROOT = Path(__file__).resolve().parents[2]
PORTABLE_NAME = "ivanka"  # copy_overlay.SOURCE


def candidate_row(plan=None, source_commit=runner.SOURCE_COMMIT):
    """Return the single immutable portable-plan row for the candidate."""
    if plan is None:
        plan = runner.load_portable_plan()
        runner.verify_portable_plan(plan)
    rows = [row for row in plan["candidates"]
            if row["source_commit"] == source_commit]
    if len(rows) != 1:
        raise ValueError("portable plan must select exactly one candidate row")
    return rows[0]


def readiness(*, plan=None, disk_usage_fn=None):
    """Read-only proof of every pinned input and the disk admission."""
    if plan is None:
        plan = runner.load_portable_plan()
        runner.verify_portable_plan(plan)
    row = candidate_row(plan)
    material = plan["materialization_receipt"]
    material_path = Path(material["path"])
    material_doc = json.loads(material_path.read_text())
    portable_path = Path(row["portable_binary_path"])
    native_path = Path(row["native_binary_path"])
    free = (disk_usage_fn or (lambda _p: shutil.disk_usage("/workspace")))(
        "/workspace").free
    return {
        "schema": SCHEMA,
        "source_commit": row["source_commit"],
        "pilot_role": row["role"],
        "prebuild_plan": {
            "sha256": runner.sha256(runner.PORTABLE_PLAN),
            "pin": runner.PORTABLE_PLAN_SHA256,
        },
        "portable_binary": {
            "path": str(portable_path),
            "sha256": runner.sha256(portable_path),
            "pin": row["portable_binary_sha256"],
        },
        "native_binary": {
            "path": str(native_path),
            "sha256": runner.sha256(native_path),
            "pin": row["native_binary_sha256"],
        },
        "materialization_receipt": {
            "path": str(material_path),
            "sha256": runner.sha256(material_path),
            "pin": material["sha256"],
            "status": material_doc.get("status"),
        },
        "independent_elf_attestation_sha256":
            material["independent_elf_evidence_sha256"],
        "disk": {
            "free_bytes": free,
            "operator_floor_bytes": OPERATOR_DISK_FLOOR,
            "guard_reserve_bytes": GUARD_RESERVE,
            "operator_ready": free >= OPERATOR_DISK_FLOOR,
        },
        "build_executed": plan.get("build_executed"),
        "execution": plan.get("execution"),
        "operator_slot_path": str(runner.SLOT_AUTH_PATH),
        "launch": ("BLOCKED until the owner confirms an exclusive shared guard "
                   "lease and grants the exact operator slot"),
    }


def stage_context(out, row):
    """Stage ONLY the pinned portable bytes into a private build context."""
    root = Path(out)
    if root.is_symlink():
        raise ValueError("evidence namespace must not be a symlink")
    context = root / "copy-overlay-context"
    if context.exists():
        raise ValueError("refuse to overwrite an existing build context")
    context.mkdir(parents=True, exist_ok=False)
    source = Path(row["portable_binary_path"])
    if source.is_symlink() or not source.is_file():
        raise ValueError("pinned portable binary missing or symlink")
    target = context / PORTABLE_NAME
    shutil.copyfile(source, target)
    os.chmod(target, 0o755)
    manifest = context / "Containerfile"
    manifest.write_text(copy_overlay.CONTAINERFILE.format(
        base="sha256:" + runner.PARENT_IMAGE))
    os.chmod(manifest, 0o400)
    # The guard itself seals a private copy read-only before exec; this
    # staging namespace stays writable so the owner can audit/rebuild it.
    if runner.sha256(target) != row["portable_binary_sha256"]:
        raise ValueError("staged bytes differ from portable pin")
    return context


def plan_for_row(row, *, context, storage_conf, base_layers, code_root=None,
                 graphroot=None):
    """Construct the exact ivanka.copy-overlay-plan.v1 for this role."""
    code_root = Path(code_root or DEFAULT_CODE_ROOT)
    helper = code_root / "benchmarks/fail_closed_guard/copy_overlay_helper.py"
    if helper.is_symlink() or not helper.is_file():
        raise ValueError("pinned copy_overlay helper missing or symlink")
    plan = {
        "schema": copy_overlay.SCHEMA,
        "base_image": "sha256:" + runner.PARENT_IMAGE,
        "source_commit": row["source_commit"],
        "context": str(context),
        "storage_conf": str(storage_conf),
        "storage_conf_sha256": runner.sha256(Path(storage_conf)),
        "graphroot": str(graphroot or runner.SHARED_PX_BOUNDARY["graphroot"]),
        "base_layers": list(base_layers),
        "artifact_sha256": row["portable_binary_sha256"],
        "artifact_mode": 0o755,
        "source": copy_overlay.SOURCE,
        "destination": copy_overlay.DESTINATION,
        "frozen_manifest_sha256": runner.FROZEN_MANIFEST_SHA256,
        "pilot_role": row["role"],
        "inherited_labels": {},
        "code_root": str(code_root),
        "code_sha256": runner.sha256(helper),
        "tag": TAG_PREFIX + row["portable_binary_sha256"][:16],
    }
    return plan


def render_invocations(*, plan_path, receipt_path, receipt_sha, out,
                       cases=None, root=None):
    """Exact operator commands; rendering them executes nothing."""
    root = str(root or runner.SHARED_PX_BOUNDARY["worker_root"])
    build_py = (
        "import json, os\n"
        "from fail_closed_guard import copy_overlay\n"
        "from expanded import p1_bounded_pilot_runner as r\n"
        "plan = json.load(open(" + repr(str(plan_path)) + "))\n"
        "res = copy_overlay.run(" + repr(root) + ", plan,\n"
        "    expected_base=r.PARENT_IMAGE, expected_commit=r.SOURCE_COMMIT,\n"
        "    graphroot=r.SHARED_PX_BOUNDARY['graphroot'],\n"
        "    env={'CONTAINERS_STORAGE_CONF': r.SHARED_PX_BOUNDARY['storage_conf'],\n"
        "         'PATH': os.environ['PATH'], 'HOME': os.environ['HOME']},\n"
        "    reserve_bytes=" + str(GUARD_RESERVE) + ")\n"
        "print(json.dumps(res, sort_keys=True))\n")
    chosen = cases or (
        "equal_strains-s000,equal_strains-s002,equal_strains-s006,"
        "equal_strains-s015,clonal-s000,coverage_hole-s002,"
        "physical-canary-R042")
    return {
        "guarded_build": (
            "PYTHONPATH=.:benchmarks python3 - <<'PY'\n" + build_py + "PY\n"),
        "postbuild_receipt": (
            "PYTHONPATH=.:benchmarks python3 -m "
            "expanded.p1_portable_build_admission receipt "
            "--plan " + shlex.quote(str(plan_path)) +
            " --result <copy-overlay-result.json> --image <postbuild-digest>"
            " --out " + shlex.quote(str(out)) +
            " --operator-confirm <owner-id>\n"),
        "verify_receipt": (
            "PYTHONPATH=.:benchmarks python3 -m "
            "expanded.p1_portable_build_admission verify --receipt " +
            shlex.quote(str(receipt_path)) + " --sha256 " + shlex.quote(str(receipt_sha)) + "\n"),
        "pilot_check": (
            "PYTHONPATH=.:benchmarks python3 -m expanded.p1_bounded_pilot_runner"
            " --check --out " + shlex.quote(str(Path(out) / "evidence/<run-id>")) +
            " --image <postbuild-digest>"
            " --portable-postbuild-receipt " + shlex.quote(str(receipt_path)) +
            " --portable-postbuild-receipt-sha256 " + shlex.quote(str(receipt_sha)) +
            " --watchdog-path " + shlex.quote(runner.SHARED_PX_BOUNDARY["watchdog_alive"]) +
            " --storage-conf " + shlex.quote(runner.SHARED_PX_BOUNDARY["storage_conf"]) +
            " --cases " + shlex.quote(chosen) + "\n"),
    }


def write_receipt(out, *, plan, result, image_digest, operator_confirm,
                  root=None, verify=True):
    """Write a SHA-pinned postbuild receipt from an ACTUAL copy_overlay result."""
    if not isinstance(operator_confirm, str) or not operator_confirm.strip():
        raise ValueError("operator-confirm owner label required")
    row = candidate_row(plan)
    result = Path(result)
    result_sha = runner.sha256(result)
    image = runner.normalize_digest(image_digest)
    if verify:
        runner.verify_copy_overlay_result(
            result, expected_sha=result_sha,
            expected_plan_sha=copy_overlay.plan_digest(plan),
            expected_image=image,
            expected_labels=runner.expected_portable_labels(row),
            root=root or runner.SHARED_PX_BOUNDARY["worker_root"])
    doc = {
        "schema": runner.PORTABLE_POSTBUILD_SCHEMA,
        "prebuild_plan_sha256": runner.PORTABLE_PLAN_SHA256,
        "build_executed": True,
        "image_identity_verified": True,
        "source_commit": row["source_commit"],
        "portable_binary_sha256": row["portable_binary_sha256"],
        "native_binary_sha256": row["native_binary_sha256"],
        "portable_binary_path": row["portable_binary_path"],
        "image_digest": image,
        "portable_image": image,
        "copy_overlay_result": {
            "path": str(result), "sha256": result_sha,
            "plan_sha256": copy_overlay.plan_digest(plan),
        },
    }
    out = Path(out)
    if out.is_symlink() or not out.is_dir():
        raise ValueError("evidence namespace missing or symlink")
    path = out / "portable-postbuild-receipt.json"
    if path.exists():
        raise ValueError("refuse to overwrite an existing postbuild receipt")
    with path.open("x") as stream:
        stream.write(json.dumps(doc, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return {"path": path, "sha256": runner.sha256(path), "doc": doc}


def verify_receipt(path, *, sha256, plan=None, root=None):
    return runner.verify_portable_postbuild_receipt(
        path, expected_sha=sha256, plan=plan,
        root=root or runner.SHARED_PX_BOUNDARY["worker_root"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    p_plan = sub.add_parser("plan")
    p_plan.add_argument("--out", required=True)
    p_plan.add_argument("--storage-conf", default=str(
        runner.SHARED_PX_BOUNDARY["storage_conf"]))
    p_plan.add_argument("--base-layers", required=True,
                        help="JSON array from read-only podman inspect of base")
    p_plan.add_argument("--code-root", default=str(DEFAULT_CODE_ROOT))
    p_plan.add_argument("--operator-confirm", required=True)
    for name in ("receipt", "verify"):
        p = sub.add_parser(name)
        if name == "receipt":
            p.add_argument("--plan", required=True)
            p.add_argument("--result", required=True)
            p.add_argument("--image", required=True)
            p.add_argument("--out", required=True)
            p.add_argument("--operator-confirm", required=True)
        else:
            p.add_argument("--receipt", required=True)
            p.add_argument("--sha256", required=True)
    args = parser.parse_args(argv)
    if args.command == "check":
        print(json.dumps(readiness(), indent=1, sort_keys=True))
        return 0
    if args.command == "plan":
        if not args.operator_confirm.strip():
            raise ValueError("operator-confirm owner label required")
        row = candidate_row()
        context = stage_context(args.out, row)
        plan = plan_for_row(
            row, context=context, storage_conf=Path(args.storage_conf),
            base_layers=json.loads(args.base_layers), code_root=args.code_root)
        path = Path(args.out) / "copy-overlay-plan.json"
        with path.open("x") as stream:
            stream.write(json.dumps(plan, sort_keys=True) + "\n")
        print(json.dumps({"plan": str(path),
                          "plan_sha256": copy_overlay.plan_digest(plan),
                          "invocations": render_invocations(
                              plan_path=path, receipt_path=Path(args.out) /
                              "portable-postbuild-receipt.json",
                              receipt_sha="<computed-after-receipt>",
                              out=args.out)}, indent=1, sort_keys=True))
        return 0
    if args.command == "receipt":
        plan = json.loads(Path(args.plan).read_text())
        receipt = write_receipt(
            args.out, plan=plan, result=args.result,
            image_digest=args.image, operator_confirm=args.operator_confirm)
        print(json.dumps({"path": str(receipt["path"]),
                          "sha256": receipt["sha256"]}, indent=1))
        return 0
    verified = verify_receipt(args.receipt, sha256=args.sha256)
    print(json.dumps({"verified": True, "image": verified["image"],
                      "source_commit": verified["source_commit"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
