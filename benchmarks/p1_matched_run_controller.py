#!/usr/bin/env python3
"""Source-only matched-run controller for the P1 ultradeep timing plan.

This controller never builds or pulls an image, starts a container, takes the
PX lock, writes a STOP sentinel or changes a deployed service. It validates a
plan emitted by :mod:`p1_ultradeep_matched_runtime` and emits a controller
record; every emitted record is ``execution: "blocked"`` and grants no authority
to arm a run.

Guard integration is reused, not duplicated: the readiness decision comes from
the plan module, the reference-blind validator and CLI template come from the
real PX execution module, and the guard-attestation fields come from the shared
``fail_closed_guard.p1_harness``. Reads, timer and image identities are not
re-pinned here; they come from the plan module unchanged.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

# Import contract for a directly executed benchmark script: the script
# directory provides the top-level plan module and the guard packages, while
# the repository root is required by the absolute ``benchmarks.*`` imports used
# transitively by px_execution. Both roots must be present before these imports,
# so the ordering below is deliberate, not an accidental late import.
_HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))

import p1_ultradeep_matched_runtime as plan  # noqa: E402
from assembler_bench import px_execution  # noqa: E402
from fail_closed_guard import p1_harness  # noqa: E402

CONTROLLER_SCHEMA = "ivanka.p1.ultradeep-matched-run-controller.v1"
REAL_TEMPLATE = "assembler_bench.px_execution.micall_argv"
GUARD_MODULE = "fail_closed_guard.p1_harness"


class Refusal(plan.Refusal):
    """Controller-level fail-closed refusal; no arm may be authorised."""


def _case_stub():
    """An in-memory case using the plan's pinned reads; nothing is written."""
    reads = plan.READS_ROOT / plan.CASES[0] / "reads"
    return type("Case", (), {
        "r1": str(reads / "R1.fastq.gz"), "r2": str(reads / "R2.fastq.gz"),
    })()


def real_cli_tail() -> list[str]:
    """Derive the exact MiCall tail from the real PX argv builder."""
    tool = next(iter(px_execution.exploratory_policy.EXPERIMENTAL))
    argv = px_execution.micall_argv(
        tool, plan.CANDIDATE_IMAGE, _case_stub(),
        pathlib.Path("/tmp/never-created-by-controller"))
    return argv[argv.index("/ivanka-timer.py"):]


def verify_cli_template(record: dict) -> dict:
    """Check every emitted argv against the real template and its blind guard."""
    expected_tail = real_cli_tail()
    for step in record.get("schedule", []):
        argv = step.get("argv", [])
        if argv[argv.index("/ivanka-timer.py"):] != expected_tail:
            raise Refusal("argv MiCall tail differs from the real PX template")
        # Reuse the real PX reference-blind validator; never reimplement it.
        px_execution.assert_reference_blind(argv)
    return {
        "real_template": REAL_TEMPLATE,
        "tail": expected_tail,
        "verified_arms": len(record.get("schedule", [])),
        "reference_blind_validator": "assembler_bench.px_execution.assert_reference_blind",
    }


def guard_integration() -> dict:
    """Report the shared guard's attestation; do not copy or restate its fields."""
    attestation = dict(p1_harness.P1_ATTESTATION)
    attestation["module"] = GUARD_MODULE
    attestation["kernel_enforcement"] = False
    return attestation


def build_controller_record(
    receipt: pathlib.Path,
    output_root: pathlib.Path,
    *,
    attestation: pathlib.Path | None = None,
    verify_files: bool = False,
) -> dict:
    """Build a source-only controller record; emit it without any live action."""
    emitted_plan = plan.build_plan(
        receipt, output_root, verify_files=verify_files, attestation=attestation)
    template = verify_cli_template(emitted_plan)
    return {
        "schema": CONTROLLER_SCHEMA,
        "plan_schema": emitted_plan["schema"],
        "inputs": emitted_plan["inputs"],
        "timer_sha256": emitted_plan["inputs"]["timer_sha256"],
        "images": emitted_plan["images"],
        "candidate_commit": emitted_plan["candidate_commit"],
        "schedule": emitted_plan["schedule"],
        "source_pins": emitted_plan["source_pins"],
        "deployed_pins": emitted_plan["deployed_pins"],
        "dependencies": emitted_plan["dependencies"],
        "cli_template": template,
        "guard_integration": guard_integration(),
        "execution": "blocked",
        "scientific_gates_changed": False,
        "formal_qualification": False,
        "privacy": emitted_plan["privacy"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--receipt", type=pathlib.Path,
        default=_HERE.parent / "docs/bench/diagnostics/p1-ultradeep-runtime-20261126.json",
    )
    parser.add_argument("--output-root", type=pathlib.Path, required=True)
    parser.add_argument("--attestation", type=pathlib.Path)
    parser.add_argument("--verify-files", action="store_true")
    parser.add_argument("--emit-plan", type=pathlib.Path)
    args = parser.parse_args()
    record = build_controller_record(
        args.receipt, args.output_root,
        attestation=args.attestation, verify_files=args.verify_files)
    text = json.dumps(record, indent=2, sort_keys=True) + "\n"
    if args.emit_plan is not None:
        target = plan.check_output_root(args.emit_plan.parent)
        if args.emit_plan.name != "controller.json":
            raise Refusal("controller file must be controller.json in a fresh root")
        target.mkdir(parents=True, exist_ok=True)
        (target / "controller.json").write_text(text)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
