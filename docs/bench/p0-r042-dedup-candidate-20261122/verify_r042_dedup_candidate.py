#!/usr/bin/env python3
"""Prospective, read-only check of the canonical-dedup candidate rule on R042.

Mirrors src/assembler/run/dedup.rs: collapse strand-canonical duplicate
molecules before output. Replays the pinned MiCall stitcher over attested
checkpoint CSVs; never writes a frozen artifact and never reads truth/score
into the candidate. This is a diagnostic of the duplicate-representation
class, NOT a physical score measurement and NOT a merge recommendation.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import os
import sys

MICALLSRC = os.environ.get("P0_MICALL_SRC", "/workspace/micall")
ARTIFACTS = os.environ.get(
    "P0_ARTIFACTS", "/workspace/micall-frozen-seven-20261117/phase-real198/artifacts"
)
SAMPLE = "63902A-V3-3-V3LOOP_S39"

sys.path.insert(0, MICALLSRC)
from micall.utils.stitched_read_counts import project_stitched_counts  # noqa: E402
from micall.utils.referencefull_contig_stitcher import (  # noqa: E402
    referencefull_contig_stitcher,
)

SOURCE_SHA256 = {
    "micall/utils/stitched_read_counts.py":
        "d6dfbd3754f115f236bdae7f6cff8e2cc4364104e863d25b50a584112b87b9fc",
    "micall/utils/referencefull_contig_stitcher.py":
        "867e323afcd5c3fc0372da7f731b05666e172969c484f82561cc7cb6ed62c44e",
}
ARMS = {
    "ivanka": ("ivanka-physical-bea55de8b5b9-9c852c0dba/ivanka",
               "a2e5c30666edbaed09a9e5a6deddaf3a4af8c575ab856709c02806cf7183b374",
               "bc99e3d5b8462262259ac319725356cf281389ea928497633985581bbd6e3f54",
               "a4011ba93eadc3a4b9e0dc9144168ff5d40f108d9368914e3a18ce527e295016",
               "90467090e59171fb359969d9b844ec1acb114ab75da8e91aa4ea171157af0616"),
    "spades": ("spades-bea55de8b5b9-cdab333f15/ivanka",
               "48ae485bf0e5f8e73636e14c4d3165e0731898430c54ccfa4518909252dfd9b2",
               "bd55a277339d59f135fcb6e329cfedc71998efbdbf99bdba9b6080190c967cc7",
               "16e8d773a6ff13cc64d77945b1afb01f0761a3da8313919f695f9cc4801e98a4",
               "7f3266ecbafcc3445ff8a5c6c8952f503a10dc21bf302fad2439c9cfa9050901"),
    "velvet": ("velvet-bea55de8b5b9-cf37d25527/ivanka",
               "9686ba28c687d8f2d1896e7d6d98533fe0dc7fb9525fa598809c73e187217be0",
               "6c2aa1deb7d8169e76399a10ebadf7a3f7d52099ee27db3a99506af796a4c467",
               "44805013a55362e178cf12fdae43097d59767c63f1eb11f250ca5862e275c9f0",
               "4a2ac8958e893efe2beb6bd8a1a29233e40bec453d685a23c6fbbfdbffa7cdec"),
}
FIELDS = ["ref", "match", "group_ref", "contig"]
FILES = ["unstitched_contigs.csv", "stitched_contigs.csv",
         "unstitched_remap_counts.csv", "contigs.csv"]
COMPLEMENT = str.maketrans("ACGT", "TGCA")


def sha256(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def arm_directory(rel: str) -> str:
    run, subdirectory = rel.split("/", 1)
    return os.path.join(ARTIFACTS, run, SAMPLE, subdirectory)


def attest() -> None:
    for rel, expected in SOURCE_SHA256.items():
        assert sha256(os.path.join(MICALLSRC, rel)) == expected, rel
    for arm, (rel, *expected) in ARMS.items():
        directory = arm_directory(rel)
        for name, digest in zip(FILES, expected):
            assert sha256(os.path.join(directory, name)) == digest, (arm, name)


def canonical_key(sequence: str) -> str:
    forward = sequence.upper()
    reverse = forward.translate(COMPLEMENT)[::-1]
    return min(forward, reverse)


def collapse(rows):
    seen = set()
    kept = []
    for row in rows:
        key = canonical_key(row["contig"])
        if key not in seen:
            seen.add(key)
            kept.append(row)
    return kept


def csv_text(rows) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


class Arm:
    def __init__(self, name):
        self.dir = arm_directory(ARMS[name][0])
        self.unstitched = self._rows(FILES[0])
        self.stitched = self._rows(FILES[1])
        self.counts_path = os.path.join(self.dir, FILES[2])
        self.frozen_final = open(os.path.join(self.dir, FILES[3])).read().strip()

    def _rows(self, name):
        with open(os.path.join(self.dir, name)) as handle:
            return [{key: row[key] for key in FIELDS} for row in csv.DictReader(handle)]

    def replay(self, unstitched=None):
        unstitched = self.unstitched if unstitched is None else unstitched
        with io.StringIO(csv_text(unstitched)) as source, \
                io.StringIO(csv_text(self.stitched)) as target, \
                open(self.counts_path) as counts:
            projected = project_stitched_counts(source, target, counts)
        output = io.StringIO()
        referencefull_contig_stitcher(
            io.StringIO(csv_text(self.stitched)), output, None, row_counts=projected)
        final = output.getvalue().strip()
        rows = final.splitlines()[1:]
        consensus = rows[-1].split(",")[-1] if rows else ""
        return {
            "all_known": len(projected) == len(self.stitched),
            "projected": projected,
            "final_ref": rows[-1].split(",")[0] if rows else None,
            "final_match": rows[-1].split(",")[1] if rows else None,
            "final_len": len(consensus),
            "final_sha": hashlib.sha256(consensus.encode()).hexdigest()[:8],
            "final_csv": final,
        }


def main() -> int:
    logging.disable(logging.WARNING)
    attest()
    result = {}
    for name in ARMS:
        arm = Arm(name)
        baseline = arm.replay()
        assert baseline["final_csv"] == arm.frozen_final, name
        result[name] = {"baseline": baseline}

    ivanka, spades, velvet = Arm("ivanka"), Arm("spades"), Arm("velvet")
    b = result["ivanka"]["baseline"]
    assert (b["final_ref"].endswith("B-KR-KJ140263-seed") and b["final_len"] == 306
            and b["final_sha"] == "edf384f9" and not b["all_known"])

    candidate = ivanka.replay(unstitched=collapse(ivanka.unstitched))
    result["ivanka"]["canonical_dedup_candidate"] = candidate
    assert candidate["all_known"]
    assert candidate["final_ref"].endswith("C-CN-KC870038-seed")
    assert candidate["final_sha"] == "2ae22268" and candidate["final_len"] == 324
    assert candidate["final_match"] == "1.0"

    controls = {"distinct_sequences_preserved": collapse([
        {"contig": "AACGT"}, {"contig": "GGGCC"}, {"contig": "TTTTT"}]) ==
        [{"contig": "AACGT"}, {"contig": "GGGCC"}, {"contig": "TTTTT"}],
        "strand_duplicate_collapsed": len(collapse([
            {"contig": "AACGT"}, {"contig": "ACGTT"}])) == 1,
        "zero_set_noop": collapse([]) == [],
    }
    assert all(controls.values()), controls
    for name, arm in (("spades", spades), ("velvet", velvet)):
        after = arm.replay(unstitched=collapse(arm.unstitched))
        assert after["final_csv"] == result[name]["baseline"]["final_csv"], name
        controls[name + "_dedup_noop"] = True
    summary = {arm: {k: {kk: vv for kk, vv in v.items() if kk != "final_csv"}
                     for k, v in arms.items()} for arm, arms in result.items()}
    summary["controls"] = controls
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
