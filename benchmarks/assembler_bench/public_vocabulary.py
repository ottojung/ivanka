"""Fail-closed external-acceptance vocabulary scanner for the public /bench/ site.

The benchmark website is a tool-neutral MiCall assembler comparison surface.
External Ivanka project acceptance is computed in private publisher modules and
never appears in a public file, schema, HTML attribute or rendered string.

The scanner intentionally matches word-bounded "gate" so the legitimate word
"aggregate" (used in mapping-diagnostic labels) is not a false positive.
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site/bench"

# Substring tokens catch inflections (qualify/qualified/qualification, ...).
# "gate" is word-bounded because "aggregate" is an ordinary statistical word.
TOKENS = (
    re.compile(r"qualif", re.IGNORECASE),
    re.compile(r"ineligib", re.IGNORECASE),
    re.compile(r"\bgates?\b", re.IGNORECASE),
    re.compile(r"px\s+candidate", re.IGNORECASE),
)
TEXT_SUFFIXES = frozenset((".html", ".js", ".css", ".json", ".md"))


def find_tokens(text):
    """Return every forbidden token found in a text blob, in stable order."""
    return [token.pattern for token in TOKENS if token.search(text)]


def scan_tree(site=SITE, *, include_browser=True):
    """Return {relative_path: [token, ...]} for every non-clean public file.

    ``include_browser=False`` restricts the scan to the JSON data published
    under ``data/``. The browser layer is owned by a separate worker; the
    full-tree form is the deployment gate once that layer lands.
    """
    source = Path(site)
    hits = {}
    paths = sorted(source.rglob("*")) if source.exists() else []
    for path in paths:
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if not include_browser and "data" not in path.relative_to(source).parts:
            continue
        found = find_tokens(path.read_text(encoding="utf-8"))
        if found:
            hits[str(path.relative_to(source))] = found
    return hits


def scan_data_files(site=SITE):
    """Strict data-only entry point used by the publication regression test."""
    return scan_tree(site, include_browser=False)


def assert_clean(site=SITE, *, include_browser=False):
    """Raise if any public file still carries external acceptance vocabulary."""
    hits = scan_tree(site, include_browser=include_browser)
    if hits:
        detail = "; ".join(f"{name}: {','.join(tokens)}"
                           for name, tokens in hits.items())
        raise ValueError("external acceptance vocabulary in public site: " + detail)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=SITE)
    parser.add_argument("--data-only", action="store_true",
                        help="scan only published JSON data")
    args = parser.parse_args()
    hits = scan_tree(args.site, include_browser=not args.data_only)
    if hits:
        for name, tokens in hits.items():
            print("VOCABULARY", name, ",".join(tokens), file=sys.stderr)
        return 1
    print("PUBLIC_VOCABULARY_CLEAN", len(list(Path(args.site).rglob("*"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
