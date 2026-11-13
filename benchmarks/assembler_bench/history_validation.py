"""Validate immutable, privacy-safe MiCall execution snapshots."""
import json
import math
import re
from pathlib import Path

from benchmarks.expanded.adapters import ASSEMBLERS
from benchmarks.expanded.micall_dominant import SCORE_ORIGIN
from .archive_sources import digest, is_hash
from .hxb2_preview import COHORT_SHA
from .psi_matrix import matrix
from .public_dominance import rows_for
from .public_metrics import CATALOG

TOOLS = set(ASSEMBLERS)
ID = re.compile(r"^[a-z0-9_-]+$")
URL = "https://github.com/ottojung/MiCall/tree/"
SENSITIVE = re.compile(
    r"/workspace/|/home/|\.fastq(?:\.gz)?|patient[-_](id|name)|"
    r"private[-_](?:sample|file)|_R[12]_[0-9]{3}", re.I)


def checked_run(run):
    if (run.get("schema") != "ivanka.assembler-bench.public.v1"
            or run.get("status") != "ineligible"
            or run.get("eligible_for_expanded") is not False
            or run.get("expanded_status") != "incomplete"
            or run.get("score_origin") != SCORE_ORIGIN
            or run.get("cohort") not in ("real", "synthetic")
            or set(run.get("tools", [])) != TOOLS
            or set(run.get("images", {})) != TOOLS
            or len(set(run["tools"])) != len(TOOLS)):
        raise ValueError("invalid archived benchmark metadata")
    expected = 400 if run["cohort"] == "synthetic" else 198
    samples = run.get("samples")
    if (run.get("expected_sample_count") != expected
            or not isinstance(samples, list)
            or not 0 < len(samples) <= expected
            or run.get("sample_count") != len(samples)
            or run.get("psi") != {}):
        raise ValueError("archived sample counts/qualification are invalid")
    archive = run.get("archive", {})
    if (archive.get("schema")
            != "ivanka.assembler-bench.execution-archive.v1"
            or not all(is_hash(archive.get(field)) for field in (
                "manifest_sha256", "results_sha256",
                "source_attestation_sha256"))):
        raise ValueError("missing source evidence digest")
    proof = run.get("micall_fork_provenance", {})
    images = proof.get("images", {})
    if (proof.get("status") != "archived"
            or proof.get("attestation_sha256")
            != archive["source_attestation_sha256"]
            or not is_hash(proof.get("base_image_sha256"))
            or set(images) != TOOLS):
        raise ValueError("archived sources do not match attestation")
    for tool, profile in images.items():
        commit = profile.get("source_commit")
        if (not isinstance(commit, str) or len(commit) != 40
                or set(commit) - set("0123456789abcdef")
                or profile.get("image_sha256") != run["images"][tool]
                or not is_hash(run["images"][tool])
                or profile.get("source_url") != URL + commit):
            raise ValueError("archived image or immutable link mismatched")
    if run.get("source_commit") != images["iva"]["source_commit"]:
        raise ValueError("archived source commit mismatch")
    if run["cohort"] == "synthetic" and (
            run.get("hxb2_truth_verified") is not True
            or run.get("cohort_manifest_sha256") != COHORT_SHA):
        raise ValueError("archived synthetic truth not authenticated")
    seen = set()
    for case in samples:
        alias = case.get("alias")
        prefix = "H" if run["cohort"] == "synthetic" else "R"
        if (not isinstance(alias, str) or not re.fullmatch(
                prefix + r"[0-9]{3}", alias) or alias in seen):
            raise ValueError("archived sample alias unsafe/duplicated")
        seen.add(alias)
        if (run["cohort"] == "synthetic"
                and not re.fullmatch(r"[a-z0-9_]+",
                                     case.get("family", ""))):
            raise ValueError("synthetic mechanism name invalid")
        if any(set(case.get(field, {})) != TOOLS for field in (
                "score", "seconds", "source_sha256")):
            raise ValueError("archived sample arm matrix incomplete")
        failed = case.get("failures")
        if (not isinstance(failed, list) or len(set(failed)) != len(failed)
                or set(failed) - TOOLS):
            raise ValueError("archived failed-arm list invalid")
        for tool in TOOLS:
            score, sec, sha = (case[key][tool] for key in
                               ("score", "seconds", "source_sha256"))
            for value in (score, sec):
                if value is not None and (type(value) not in (float, int)
                        or not math.isfinite(value) or value < 0):
                    raise ValueError("archived score/runtime invalid")
            if sec is not None and not 0 < sec <= 1800:
                raise ValueError("invalid executed MiCall duration")
            if sha is not None and not is_hash(sha):
                raise ValueError("archived source output hash invalid")
            if tool in failed and (score is not None or sec is not None):
                raise ValueError("failed tool shown with valid score")
        has_seven = not failed and all(
            case["score"][tool] is not None and
            case["seconds"][tool] is not None for tool in TOOLS)
        outcome = ("failure" if failed else
                   "success" if has_seven else "incomplete")
        if case.get("outcome") != outcome:
            raise ValueError("archived case outcome inconsistent")
        floor = (case["score"]["ivanka"] >= .9*max(
            case["score"][name] for name in TOOLS if name != "ivanka")
            if has_seven else None)
        if case.get("floor_ok") is not floor:
            raise ValueError("archived case alignment floor inconsistent")
        for tool, metrics in case.get("diagnostics", {}).items():
            if tool not in TOOLS or set(metrics) - set(CATALOG):
                raise ValueError("archived diagnostic key unknown")
            if any(type(v) not in (float, int)
                   or not math.isfinite(v) or v < 0
                   for v in metrics.values()):
                raise ValueError("archived diagnostic measurement invalid")
    verified = matrix(rows_for(run), run["tools"],
                      expected=expected, eligible=False)
    if run.get("dominance_matrix") != verified:
        raise ValueError("archived pairwise Ψ evidence mismatch")


def check_history(history, current):
    if (history.get("schema") !=
            "ivanka.assembler-bench.execution-history.v1"
            or not isinstance(history.get("runs"), list)
            or not history["runs"]):
        raise ValueError("missing immutable execution history")
    ids = set(current)
    for run in history["runs"]:
        name = run.get("id")
        if (not isinstance(name, str) or not ID.fullmatch(name)
                or name in ids):
            raise ValueError("duplicate or invalid archived run identifier")
        ids.add(name)
        checked_run(run)
    if SENSITIVE.search(json.dumps(history)):
        raise ValueError("private data in archived public results")
    return len(history["runs"])


def validate_archive_file(path, current):
    return check_history(json.loads(Path(path).read_text()), current)
