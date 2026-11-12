"""Fail-closed, privacy-checked, static GitHub Pages publisher for /bench/."""
import argparse
import json
import re
import shutil
from pathlib import Path

from .publication import SCHEMA

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site/bench"
ALIAS = re.compile(r"^R[0-9]{3}$")
RUN = re.compile(r"^[a-zA-Z0-9_-]+$")
SECRET = re.compile(r"/workspace/|/home/|_R[12]_[0-9]{3}|"
                    r"\.fastq(?:\.gz)?|private[-_]sample|patient[-_](?:id|name)",
                    re.IGNORECASE)


def validate_public_site(site=SITE):
    source = Path(site)
    required = ("index.html", "style.css", "app.js", "data/runs.json")
    if any(not (source / name).is_file() for name in required):
        raise ValueError("incomplete /bench site assets")
    html = (source / "index.html").read_text()
    js = (source / "app.js").read_text()
    for link in ('href="./style.css"', 'src="./app.js"',
                 'id="runSelect"', 'id="resultRows"',
                 'id="comparisonChart"', 'id="evidenceContent"',
                 'id="detailPanel"'):
        if link not in html:
            raise ValueError(f"missing standalone Pages asset/control: {link}")
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
    if SECRET.search(json.dumps(report)):
        raise ValueError("private sample path or identifier in public report")
    return len(report["runs"])


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
        '<title>Ivanka · Assembler Bench</title>'
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
