"""Scrub a generated resource-policy report into the neutral public schema.

The pinned resource reporter is historical evidence, not a website publisher.
Its acceptance-flavoured schema and note are rewritten at the publication
boundary; all limits and per-arm classifications are preserved unchanged.
"""
import argparse
import json
import os
import stat
from pathlib import Path

from .public_view import assert_clean_object, sanitize_document


def scrub(path):
    source = Path(path)
    document = sanitize_document(json.loads(source.read_text()))
    assert_clean_object(document)
    payload = (json.dumps(document, sort_keys=True,
                          separators=(",", ":")) + "\n").encode()
    temporary = source.with_name("." + source.name + ".neutral.tmp")
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, stat.S_IMODE(source.stat().st_mode))
    os.replace(temporary, source)
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, required=True)
    args = parser.parse_args()
    result = scrub(args.path)
    print("RESOURCE_POLICY_NEUTRAL", result["schema"],
          result["max_wall_seconds"], result["max_rss_bytes"])


if __name__ == "__main__":
    main()
