"""Fail-closed, privacy-checked, static GitHub Pages publisher for /bench/."""
import argparse
import json
import re
import shutil
import math
from pathlib import Path

from .publication import SCHEMA
from .site_validation import check_mapping_snapshot, check_matrices

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site/bench"
ALIAS = re.compile(r"^R[0-9]{3}$")
HXB2_ALIAS = re.compile(r"^H[0-9]{3}$")
HXB2_COHORT_SHA = "964fff8226beef4787226a5542dc2667fff0102bea0b4f4694686b11af1f7f5a"
RUN = re.compile(r"^[a-zA-Z0-9_-]+$")
SECRET = re.compile(r"/workspace/|/home/|_R[12]_[0-9]{3}|"
                    r"\.fastq(?:\.gz)?|private[-_]sample|patient[-_](?:id|name)",
                    re.IGNORECASE)


def validate_public_site(site=SITE):
    source = Path(site)
    required = ("index.html", "style.css", "subjects.js",
                "rankings.js", "app.js",
                "data/runs.json",
                "data/mapping-diagnostics.json")
    if any(not (source / name).is_file() for name in required):
        raise ValueError("incomplete /bench site assets")
    html = (source / "index.html").read_text()
    js = (source / "app.js").read_text()
    for link in ('href="./style.css"', 'src="./subjects.js"',
                 'src="./app.js"',
                 'id="runSelect"', 'id="resultRows"',
                 'id="comparisonChart"', 'id="evidenceContent"',
                 'id="detailPanel"', 'id="dominanceMatrix"',
                 'id="dominanceSubjects"', 'id="subjectSearch"',
                 'id="subjectsCount"', 'id="firstTool"',
                 'id="diagnosticMatrix"', 'id="diagnosticMetric"',
                 'id="diagnosticExplanation"', 'id="diagnosticChart"',
                 'id="singleDirection"'):
        if link not in html:
            raise ValueError(f"missing standalone Pages asset/control: {link}")
    if 'fetch("./data/mapping-diagnostics.json"' not in js:
        raise ValueError("mapping report must be fetched from same origin")
    if (any(name not in js for name in
            ("function drawDominance()", "function drawDiagnostics()",
             "function drawSubjectControls()", "function selectedSubjects()",
             "BenchRanks.summary(", "BenchRanks.pairs(",
             "info.description", "info.denominator",
             "state.diagnostics?.metric_catalog"))):
        raise ValueError("public site lacks checkbox subjects or metric explanations")
    ranks = (source / "rankings.js").read_text()
    if (any(name not in ranks for name in
            ("function summary(", "function measurements(", "function pairs(",
             "expected_sample_count", "snapshot.tools?.[tool]?.values?.[key]"))):
        # The selector must rank any real metric using only measured cases.
        raise ValueError("public site lacks comparable numeric metric ranking")
    if (not (html.index('class="compare"') < html.index('class="samples"')
             < html.index('class="dominance"'))):
        raise ValueError("single-metric and case comparisons must precede Ψ")
    if "id=\"scoreView\"" in html or "id=\"timeView\"" in html:
        raise ValueError("alignment/runtime-only comparison controls forbidden")
    subjects = (source / "subjects.js").read_text()
    if (any(name not in subjects for name in
            ("function conjunction(", "function criterion(", "does-not-dominate",
             "incomplete", "unresolved"))):
        raise ValueError("public matrix subject conjunction is not fail-closed")
    if "function cellText(" in js or "obs.gains" in js[
            js.index("function drawDominance()"):js.index("function render()")]:
        raise ValueError("dominance matrix cells must contain verdicts, not counts")
    if (any(name not in js for name in ("BenchSubjects.verdict(result.status)",
             "esc(verdict.label)", "title=")) or
            "function verdict(status)" not in subjects or
            'class="dominance-legend"' not in html):
        raise ValueError("matrix lacks strict yes/no/unknown verdict semantics")
    if 'fetch("./data/runs.json"' not in js:
        raise ValueError("client must fetch same-origin relative data")
    if re.search(r"<script[^>]*src=[\"']https?://", html):
        raise ValueError("third-party script dependency forbidden")
    report = json.loads((source / "data/runs.json").read_text())
    if report.get("schema") != SCHEMA or not isinstance(report.get("runs"), list):
        raise ValueError("unsupported public result schema")
    if not report["runs"] or report.get("expanded_qualification") != "incomplete":
        raise ValueError("current public gate status missing")
    ids = set()
    for run in report["runs"]:
        if not RUN.fullmatch(run["id"]) or run["id"] in ids:
            raise ValueError("invalid or duplicate public run identifier")
        ids.add(run["id"])
        if run["status"] not in ("passed-original-only", "ineligible", "incomplete"):
            raise ValueError("unattested public qualification status")
        if run["status"] == "passed-original-only":
            if (run["cohort"] != "real" or run["sample_count"] != 198 or
                    len(run.get("samples", [])) != 198 or
                    not run["psi"]["alignment"]["positive_all_nonnegative"] or
                    not run["psi"]["runtime"]["positive_all_nonnegative"] or
                    run["eligible_for_expanded"]):
                raise ValueError("incorrect original-gate provenance")
            seen = set()
            for sample in run["samples"]:
                if not ALIAS.fullmatch(sample["alias"]) or sample["alias"] in seen:
                    raise ValueError("public aliases are unsafe or duplicated")
                seen.add(sample["alias"])
                if set(sample) != {"alias", "score", "seconds", "floor_ok", "outcome"}:
                    raise ValueError("unexpected public sample metadata")
                if not sample["floor_ok"] or sample["outcome"] != "success":
                    raise ValueError("unreported sample failure")
        if run["status"] == "ineligible":
            if run["eligible_for_expanded"] or run.get("psi"):
                raise ValueError("ineligible run falsely presented as passing")
        if run["status"] == "incomplete":
            verify_hxb2_preview(run)
    check_matrices(report)
    check_mapping_snapshot(source, report)
    if SECRET.search(json.dumps(report)):
        raise ValueError("private sample path or identifier in public report")
    return len(report["runs"])


def verify_hxb2_preview(run):
    """Incomplete HXB2 cases must be honestly represented, never called wins."""
    from benchmarks.expanded.adapters import ASSEMBLERS
    required = set(ASSEMBLERS)
    if (run.get("cohort") != "synthetic"
            or run.get("hxb2_truth_verified") is not True
            or run.get("eligible_for_expanded") is not False
            or run.get("expanded_status") != "incomplete"
            or run.get("cohort_manifest_sha256") != HXB2_COHORT_SHA
            or run.get("expected_sample_count") != 400
            or run.get("psi") != {}
            or set(run.get("tools", [])) != required
            or set(run.get("images", {})) != required):
        raise ValueError("incomplete HXB2 run has incorrect scientific evidence")
    if (any(not re.fullmatch("[0-9a-f]{64}", value)
            for value in run["images"].values())
            or not re.fullmatch("[0-9a-f]{64}", run.get("diagnostic_sha256", ""))):
        raise ValueError("HXB2 run missing immutable tool/output hashes")
    samples = run.get("samples")
    if (not isinstance(samples, list) or not 1 <= len(samples) <= 400
            or run.get("sample_count") != len(samples)
            or len({sample.get("alias") for sample in samples}) != len(samples)):
        raise ValueError("incomplete HXB2 run has invalid sample count/aliases")
    for sample in samples:
        if (not HXB2_ALIAS.fullmatch(sample["alias"])
                or set(sample) != {"alias", "family", "score", "seconds",
                                   "failures", "outcome", "floor_ok"}
                or not re.fullmatch("[a-z0-9_]+", sample["family"])
                or set(sample["score"]) != required
                or set(sample["seconds"]) != required
                or not isinstance(sample["failures"], list)
                or len(set(sample["failures"])) != len(sample["failures"])
                or set(sample["failures"]) - required
                or sample["outcome"] != ("failure" if sample["failures"]
                                         else "success")):
            raise ValueError("incomplete HXB2 result has invalid sample evidence")
        if sample["failures"]:
            if sample["floor_ok"] is not None:
                raise ValueError("failed arm cannot have a qualified floor")
        else:
            highest = max(sample["score"][tool] for tool in required
                          if tool != "ivanka")
            if sample["floor_ok"] is not (
                    sample["score"]["ivanka"] >= 0.9 * highest):
                raise ValueError("HXB2 per-sample floor is misreported")
        for tool in required:
            quality, seconds = sample["score"][tool], sample["seconds"][tool]
            if tool in sample["failures"]:
                if quality is not None or seconds is not None:
                    raise ValueError("failed competitor is shown as success")
            elif (type(quality) not in (float, int)
                  or not math.isfinite(quality) or not 0 <= quality <= 1
                  or type(seconds) not in (float, int)
                  or not math.isfinite(seconds) or not 0 < seconds <= 1800):
                raise ValueError("unverified success metric in HXB2 result")


def build(output, site=SITE):
    checked = validate_public_site(site)
    destination = Path(output)
    if destination.exists():
        raise FileExistsError("refusing to overwrite an existing Pages build")
    destination.mkdir(parents=True)
    shutil.copytree(site, destination / "bench")
    (destination / ".nojekyll").write_text("")
    (destination / "index.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Assembler Bench · MiCall comparisons</title>'
        '<meta http-equiv="refresh" content="0;url=./bench/">'
        '<a href="./bench/">Open the Assembler Bench</a></html>')
    print(f"PAGES_BUILD_VERIFIED runs={checked} route=/bench/ path={destination}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.output)


if __name__ == "__main__":
    main()
