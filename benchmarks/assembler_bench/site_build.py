"""Fail-closed, privacy-checked, static GitHub Pages publisher for /bench/."""
import argparse
import json
import math
import re
import shutil
from pathlib import Path

from .public_fork_provenance import check as check_fork_provenance
from .public_validation import check_public_site
from .public_vocabulary import assert_clean
from .publication import SCHEMA
from .site_validation import check_mapping_snapshot

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
                "rankings.js", "distribution.js", "compare_views.js",
                "overview.js", "app.js",
                "data/runs.json", "data/history.json",
                "data/mapping-diagnostics.json",
                "data/live-fork-attestation.json",
                "data/assembler-evidence.json")
    if any(not (source / name).is_file() for name in required):
        raise ValueError("incomplete /bench site assets")
    html = (source / "index.html").read_text()
    js = (source / "app.js").read_text()
    for link in ('href="./style.css"', 'src="./subjects.js"',
                 'src="./app.js"', 'src="./compare_views.js"',
                 'id="runSelect"', 'id="resultRows"',
                 'id="comparisonChart"', 'id="distributionPanel"',
                 'id="distributionChart"', 'id="distributionClose"',
                 'id="sampleDialog"', 'id="sampleDialogMetrics"',
                 'id="sampleDialogClose"', 'id="dominanceMatrix"',
                 'id="dominanceSubjects"', 'id="subjectSearch"',
                 'id="subjectsCount"', 'id="firstTool"',
                 'id="diagnosticMetric"',
                 'id="diagnosticExplanation"',
                 'id="singleDirection"', 'id="psiExponent"',
                 'id="psiMetric"', 'id="momentLegend"',
                 ):
        if link not in html:
            raise ValueError(f"missing standalone Pages asset/control: {link}")
    if ("BenchDistribution.model(values)" not in js
            or 'button[data-tool]' not in js
            or "function drawDistribution()" not in js):
        raise ValueError("ranking bars must reveal metric distributions")
    views = (source / "compare_views.js").read_text()
    if ("BenchViews.sampleTable(" not in js
            or "BenchViews.matrixPlots(" not in js
            or "function matrixPlots(" not in views
            or "function sampleTable(" not in views):
        raise ValueError("missing all-metric sample dialog or paired density charts")
    if 'id="realProgress"' in html:
        raise ValueError("obsolete physical-progress banner reintroduced")
    if ('id="toolProgress"' in html or "Completed MiCall arms" in js
            or "Cases with results" in js or "run.status_reason" in js):
        raise ValueError("benchmark overview cannot be an execution dashboard")
    if ('src="./overview.js"' not in html
            or not (source / "overview.js").is_file()
            or "BenchOverview.summary(" not in js
            or "BenchOverview.notice(" not in js
            or "BenchOverview.coverage(" not in js):
        raise ValueError("missing results-based overview or minimal top notice")
    if ('id="comparatorProgress"' in html
            or (source / "comparator-progress.js").exists()
            or (source / "data/comparator-progress.json").exists()):
        raise ValueError("rerun-specific dashboard must not diverge from runs.json")
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
    if (not (html.index('class="compare"') < html.index('class="dominance"')
             < html.index('class="samples"'))):
        raise ValueError("single-metric, Ψ matrix, and case table out of order")
    if "id=\"scoreView\"" in html or "id=\"timeView\"" in html:
        raise ValueError("alignment/runtime-only comparison controls forbidden")
    subjects = (source / "subjects.js").read_text()
    if (any(name not in subjects for name in
            ("function conjunction(", "function criterion(", "does-not-dominate",
             "incomplete", "unresolved"))):
        raise ValueError("public matrix subject conjunction is not fail-closed")
    if "function cellText(" in js:
        raise ValueError("dominance cells must not replace proof with numeric scores")
    if (any(name not in js for name in
            ("BenchSubjects.observedVerdict(result)", "esc(verdict.label)",
             "BenchSubjects.verdict(result.status)",
             "BenchSubjects.evidence(result)", 'class="dom-verdict"',
             "evidence.description", 'esc(label)')) or
            any(name not in subjects for name in
                ("function observedVerdict(result)", "function verdict(status)",
                 "function evidence(result, limit=2)",
                 'item.paired+"/"+item.expected')) or
            'class="dominance-key"' not in html or
            any(marker in js[js.index("function drawDominance()"):
                              js.index("function render()")]
                for marker in ('class="dom-preview"', 'class="dom-preview-row"',
                               'class="dom-scope-label"'))):
        raise ValueError("matrix must show a compact verdict and preserve detailed evidence")
    if (any(option not in html for option in
            ('<option value="all" selected>All</option>',
             '<option value="0">0</option>',
             '<option value="1">1</option>',
             '<option value="2">2</option>')) or
            'function moment(entry, exponent)' not in subjects or
            'BenchSubjects.moment(' not in js or
            'params.set("psi_r",state.psiExponent)' not in js or
            'params.set("psi_metric",state.psiMetric)' not in js):
        raise ValueError("matrix lacks checked-metric Ψ(0,1,2) numeric views")
    if 'fetch("./data/runs.json"' not in js:
        raise ValueError("client must fetch same-origin relative data")
    if any(token in js for token in ("setInterval(", "setTimeout(",
                                      "EventSource(", "WebSocket(")):
        raise ValueError("static benchmark website must never poll or stream")

    if re.search(r"<script[^>]*src=[\"']https?://", html):
        raise ValueError("third-party script dependency forbidden")
    report = json.loads((source / "data/runs.json").read_text())
    if report.get("schema") != SCHEMA or not isinstance(report.get("runs"), list):
        raise ValueError("unsupported public result schema")
    checked = check_public_site(source)
    for run in report["runs"]:
        if not RUN.fullmatch(run["id"]):
            raise ValueError("invalid public run identifier")
        check_fork_provenance(source, run)
    check_mapping_snapshot(source, report)
    if SECRET.search(json.dumps(report)):
        raise ValueError("private sample path or identifier in public report")
    return checked


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
