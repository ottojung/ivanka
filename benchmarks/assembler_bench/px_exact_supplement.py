"""Versioned, hash-bound supplemental exact-coverage diagnostics for PX.

Separate from the immutable ``px_metrics.record`` diagnostics: a supplement is
computed posthoc, exclusively created in an isolated directory, and joined into
the public view only after every source hash matches the original receipt,
image, final MAX consensus, read pair and pinned MiCall module.

This module never launches a benchmark, never rewrites a diagnostics record,
and never emits clinical identities. It only supplements a genuinely
unavailable exact-coverage diagnostic; an already extracted record is left
untouched. Source-only PR; not applied to the live tree.
"""
import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

# Reviewed, explicit integration. No auto-discovery and no installs.
VENV_PYTHON = "/workspace/micall-frozen-seven-20261117/bench-ci-venv/bin/python"
MICALL_SOURCE_ROOT = "/workspace/micall-frozen-seven-20261117/ivanka"
PINNED_MODULE_PATH = (MICALL_SOURCE_ROOT
                      + "/micall/utils/exact_coverage.py")
MODULE_FILE = Path(__file__).resolve()
BENCHMARK_SOURCE_ROOT = MODULE_FILE.parents[1]   # .../benchmarks
REPO_ROOT = MODULE_FILE.parents[2]              # worktree root
PHYSICAL_ROOT = Path("/workspace/denovo-example-io-1")

PINNED_MODULE_SHA256 = "3d3b3d38ea83d1a3bb6872ef20cc5a8f1177ee3e6a272c635aa28dd77ba6f4ee"
SCHEMA = "ivanka.px.exact-supplement.v1"
SCHEMA_VERSION = 1
METHOD = "micall-longest-final-MAX-exact-v2"
OVERLAP_SIZE = 70
GENERATOR_NAME = "px_exact_supplement"
GENERATOR_VERSION = "1.0.0"
THREAD_ENV = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
              "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")
FORBIDDEN_PUBLIC = ("63899A", "V3LOOP", "hxb2", "denovo-example-io-1")
CSV_SUFFIX = ".exact_coverage.csv"
EVIDENCE_KEYS = frozenset((
    "implementation_sha256", "method", "overlap_size",
    "coverage_csv_sha256", "source_conseq_sha256", "image_sha256",
    "source_fastq_sha256", "diagnostics_record_sha256", "supplement_sha256",
))


def stream_sha256(path, chunk_size=1024 * 1024):
    """Hash a file in bounded chunks (large FASTQs never load into memory)."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256(path):
    return stream_sha256(path)


def json_bytes(obj):
    return (json.dumps(obj, sort_keys=True, indent=2) + "\n").encode()


def verify_pinned_module():
    """Hash the exact expected file BEFORE import; verify resolved path+digest."""
    expected = Path(PINNED_MODULE_PATH)
    if not expected.is_file():
        raise ValueError("pinned exact-coverage module file is absent")
    pre = stream_sha256(expected)          # pre-import hash of the exact file
    if pre != PINNED_MODULE_SHA256:
        raise ValueError("pinned module hash mismatch before import: " + pre)
    from micall.utils import exact_coverage
    resolved = Path(exact_coverage.__file__).resolve()
    if resolved != expected.resolve():
        raise ValueError("imported module resolved path mismatch: " + str(resolved))
    post = stream_sha256(resolved)         # digest of the imported resolved file
    if post != PINNED_MODULE_SHA256:
        raise ValueError("imported module digest mismatch: " + post)
    return exact_coverage


def venv_env():
    """Environment for the reviewed venv + frozen source roots, single-threaded."""
    env = os.environ.copy()
    roots = [str(BENCHMARK_SOURCE_ROOT), str(REPO_ROOT), str(MICALL_SOURCE_ROOT)]
    if env.get("PYTHONPATH"):
        roots.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(roots)
    for key in THREAD_ENV:
        env[key] = "1"
    return env


def ensure_venv():
    """Re-exec as a MODULE under the pinned venv; direct-file relative imports fail."""
    if Path(sys.executable).resolve() == Path(VENV_PYTHON).resolve():
        return
    cmd = ["nice", "-n", "19", "taskset", "-c", "0", VENV_PYTHON,
           "-m", "assembler_bench.px_exact_supplement", *sys.argv[1:]]
    raise SystemExit(subprocess.call(cmd, env=venv_env()))


def receipt_id(arm):
    from . import px_cohort_scheduler as sched
    return sched.receipt_id(arm)


def receipt_path(root, arm):
    return Path(root) / "receipts" / (receipt_id(arm) + ".json")


def receipt_arm(receipt):
    return {key: receipt[key] for key in ("tool_id", "cohort", "alias")}


def verify_attested(path, expected=None, index=None, key=None):
    """Verify a file digest against its sidecar and, optionally, an index."""
    digest = stream_sha256(path)
    if expected is not None and digest != expected:
        raise ValueError("attested digest mismatch: " + str(path))
    sidecar = Path(str(path) + ".sha256")
    if sidecar.is_file() and sidecar.read_text().strip() != digest:
        raise ValueError("attestation sidecar mismatch: " + str(path))
    if index is not None and index.get(key or path.stem) != digest:
        raise ValueError("receipt differs from case index: " + str(path))
    return digest


def _case_paths(root, arm, receipt):
    from . import px_cohort_scheduler as sched
    from . import real_public

    alias = receipt["alias"].removeprefix("PX-")
    samples = real_public.sample_aliases(PHYSICAL_ROOT)
    sample = next((name for name, public in samples.items()
                   if public == alias), None)
    if sample is None:
        raise ValueError("PX alias is not a canonical physical case")
    folder = PHYSICAL_ROOT / "samples" / sample
    reads = [next(folder.glob("*_" + mate + "_001.fastq.gz"), None)
             for mate in ("R1", "R2")]
    if any(path is None for path in reads):
        raise FileNotFoundError("original paired read files unavailable")
    output_dir = Path(root) / "outputs" / (arm["tool_id"] + "-" + arm["alias"])
    artifact = output_dir / sched.MAX_ARTIFACT
    if not artifact.is_file():
        artifact = output_dir / "scratch" / sched.MAX_ARTIFACT
    return reads, artifact


def compute_one(root, arm, receipt, output_root):
    """Compute and seal one versioned supplement. No benchmark is launched."""
    from .metric_catalog_exact import catalog, values as exact_values
    from produce_exact_coverage import generate

    verify_pinned_module()
    name = receipt_id(arm)                       # full ID, matches ingest lookup
    diag_path = Path(root) / "diagnostics" / (name + ".json")
    diagnostics = json.loads(diag_path.read_bytes())
    current = diagnostics["metrics"]["exact_coverage"]
    if current.get("status") != "unavailable":
        return None                             # never overwrite an extracted record
    if not isinstance(current.get("unavailable_reason"), str):
        raise ValueError("unavailable exact metric lacks an explicit reason")

    reads, artifact = _case_paths(root, arm, receipt)
    expected = receipt["output_sha256"]
    if not artifact.is_file() or stream_sha256(artifact) != expected:
        raise ValueError("final MAX consensus source digest mismatch")
    fastq_sha = [stream_sha256(path) for path in reads]   # streaming
    if fastq_sha != [receipt["input_sha256"]["R1"],
                     receipt["input_sha256"]["R2"]]:
        raise ValueError("original FASTQ hashes changed")
    receipt_sha = verify_attested(receipt_path(root, arm))
    diag_sha = verify_attested(diag_path)

    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    csv_path = output_root / (name + CSV_SUFFIX)
    report_path = output_root / (name + ".json")
    if csv_path.exists() or report_path.exists():
        raise FileExistsError("supplement already exists: " + str(output_root))
    report = generate(*reads, artifact, csv_path, overlap_size=OVERLAP_SIZE)
    values = exact_values(report)               # exact catalog keys only
    if set(values) != frozenset(catalog()):
        raise ValueError("generator produced unexpected metric keys")

    supply = {
        "schema": SCHEMA, "schema_version": SCHEMA_VERSION,
        "generator": {"name": GENERATOR_NAME, "version": GENERATOR_VERSION,
                      "method": METHOD, "overlap_size": OVERLAP_SIZE},
        "case": {"alias": receipt["alias"], "cohort": receipt["cohort"],
                 "tool_id": receipt["tool_id"], "receipt_sha256": receipt_sha},
        "bindings": {
            "image_sha256": receipt["image_sha256"],
            "final_conseq_sha256": expected,
            "fastq_sha256": fastq_sha,
            "module_sha256": PINNED_MODULE_SHA256,
            "overlap_size": OVERLAP_SIZE, "method": METHOD,
        },
        "diagnostics_binding": {
            "path": "diagnostics/" + name + ".json",
            "record_sha256": diag_sha,
            "original_exact_status": current["status"],
            "original_unavailable_reason": current["unavailable_reason"],
        },
        "values": values,
        "selected_sequence_sha256": report["selected_sequence_sha256"],
        "bases": report["bases"], "uncovered": report["uncovered"],
        "exact_coverage_sha256": stream_sha256(csv_path),
        "qualification_effect": "none",
    }
    assert_public_private(supply)
    with report_path.open("x") as handle:
        handle.write(json_bytes(supply).decode())
    Path(str(report_path) + ".sha256").write_text(
        stream_sha256(report_path) + "\n")
    return supply


def assert_public_private(obj):
    """Fail closed if a public artifact carries a clinical identity."""
    blob = json.dumps(obj, sort_keys=True)
    if any(token in blob for token in FORBIDDEN_PUBLIC):
        raise ValueError("clinical identity in public JSON")

    def walk(value):
        if isinstance(value, str):
            if re.fullmatch(r"[0-9a-f]{64}", value):
                return                          # SHA-256 hash, not sequence
            if re.search(r"[ACGT]{60,}", value):
                raise ValueError("raw nucleotide sequence in public JSON")
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    walk(obj)
    return obj


def join_at_publication(coverage, root, name, receipt, diagnostics,
                        supplement_root=None):
    """Join a verified supplement into the public view; fail closed otherwise."""
    if coverage.get("status") == "extracted":
        return coverage                         # never overwrite a real record
    supplement_root = Path(supplement_root or Path(root) / "supplements")
    path = supplement_root / (name + ".json")
    if not path.is_file():
        return coverage                         # keep the immutable unavailable reason
    supply = json.loads(path.read_bytes())
    assert_public_private(supply)               # no clinical strings in the artifact
    sidecar = Path(str(path) + ".sha256")
    if not sidecar.is_file() or sidecar.read_text().strip() != stream_sha256(path):
        raise ValueError("supplement hash sidecar mismatch")

    from . import px_cohort_scheduler as sched
    from .metric_catalog_exact import catalog

    binds, case, diag, gen = (supply["bindings"], supply["case"],
                              supply["diagnostics_binding"], supply["generator"])
    diag_path = Path(root) / "diagnostics" / (name + ".json")
    expected = receipt["output_sha256"]
    index = sched._load_index(root)
    checks = (
        supply.get("schema") == SCHEMA
        and supply.get("schema_version") == SCHEMA_VERSION
        and gen.get("name") == GENERATOR_NAME
        and gen.get("version") == GENERATOR_VERSION
        and gen.get("method") == METHOD
        and gen.get("overlap_size") == OVERLAP_SIZE
        and case.get("receipt_sha256") == verify_attested(
            receipt_path(root, receipt_arm(receipt)), index=index, key=name)
        and case.get("alias") == receipt["alias"]
        and case.get("cohort") == receipt["cohort"]
        and case.get("tool_id") == receipt["tool_id"]
        and diag.get("record_sha256") == verify_attested(diag_path)
        and diag.get("original_exact_status") == "unavailable"
        and binds.get("image_sha256") == receipt["image_sha256"]
        == diagnostics["image_sha256"]
        and binds.get("final_conseq_sha256") == expected
        == diagnostics["output_sha256"]
        and binds.get("fastq_sha256") == [receipt["input_sha256"]["R1"],
                                          receipt["input_sha256"]["R2"]]
        and binds.get("module_sha256") == PINNED_MODULE_SHA256
        and binds.get("method") == METHOD
        and binds.get("overlap_size") == OVERLAP_SIZE
    )
    if not checks:
        raise ValueError("exact-coverage supplement provenance disagrees")
    csv_path = supplement_root / (name + CSV_SUFFIX)
    if (not csv_path.is_file()
            or stream_sha256(csv_path) != supply.get("exact_coverage_sha256")):
        raise ValueError("supplement coverage CSV digest mismatch")
    values = supply.get("values")
    if (not isinstance(values, dict) or set(values) != frozenset(catalog())
            or any(isinstance(v, bool) or type(v) not in (int, float)
                   or not math.isfinite(v) or v < 0 for v in values.values())):
        raise ValueError("invalid supplemental exact-coverage aggregates")
    return assert_public_private({
        "status": "extracted", "unavailable_reason": None,
        "values": values, "evidence": {
            "implementation_sha256": binds["module_sha256"],
            "method": METHOD, "overlap_size": OVERLAP_SIZE,
            "coverage_csv_sha256": supply["exact_coverage_sha256"],
            "source_conseq_sha256": expected,
            "image_sha256": binds["image_sha256"],
            "source_fastq_sha256": binds["fastq_sha256"],
            "diagnostics_record_sha256": diag["record_sha256"],
            "supplement_sha256": stream_sha256(path),
        }})


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=("compute", "join"), required=True)
    p.add_argument("--root", type=Path)
    p.add_argument("--alias", action="append", dest="aliases")
    p.add_argument("--output", type=Path)
    args = p.parse_args(argv)
    if args.mode == "compute":
        ensure_venv()
        from . import px_cohort_scheduler as sched
        if args.root is None or args.output is None:
            p.error("compute needs --root and --output")
        wanted = set(args.aliases or ())
        made = []
        for identifier in sched._load_index(args.root):
            arm = sched.arm_from_receipt(args.root, identifier)
            if arm is None or (wanted and arm["alias"] not in wanted):
                continue
            receipt = sched.verify_receipt(args.root, arm)
            if receipt is None or receipt["outcome"] != "success":
                continue
            if compute_one(args.root, arm, receipt, args.output) is not None:
                made.append(receipt_id(arm))
        print(json.dumps({"schema": "ivanka.px.exact-supplement.run.v1",
                          "computed": made}, sort_keys=True))
    else:
        path = Path(args.output)
        supply = json.loads(path.read_bytes())
        if supply.get("schema") != SCHEMA:
            p.error("not an exact-coverage supplement")
        print(json.dumps({"schema": SCHEMA, "valid_shape": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
