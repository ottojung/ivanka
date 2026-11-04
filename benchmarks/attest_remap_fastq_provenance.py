"""Attest original FASTQ sequence/quality origin of paired MiCall remap rows.

A remap row may duplicate a processed mate's sequence. Authentic origin is
NOT proof of an independent physical molecule or complete haplotype phase.
"""
import argparse
import csv
import gzip
import hashlib
import json
import os
from collections import defaultdict
from itertools import zip_longest
from pathlib import Path

from shared_block_consensus_candidate import _strict_pair

_COMPLEMENT = str.maketrans("ACGTN", "TGCAN")


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def fastq(path, mate):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt") as stream:
        while header := stream.readline():
            sequence, plus, quality = (stream.readline().rstrip("\r\n")
                                       for _ in range(3))
            parts = header.rstrip().split()
            if not parts or not parts[0].startswith("@") or not plus.startswith("+"):
                raise ValueError("Malformed original FASTQ record")
            name = parts[0][1:]
            if name.endswith(("/1", "/2")):
                if not name.endswith("/" + str(mate)):
                    raise ValueError("Wrong FASTQ mate designator")
                name = name[:-2]
            elif len(parts) > 1 and parts[1][:2] in ("1:", "2:"):
                if not parts[1].startswith(str(mate) + ":"):
                    raise ValueError("Wrong FASTQ mate metadata")
            if (not name or not sequence or len(sequence) != len(quality)
                    or set(sequence.upper()) - set("ACGTN")
                    or any(not 33 <= ord(q) <= 126 for q in quality)):
                raise ValueError("Malformed FASTQ bases or qualities")
            yield name, sequence.upper(), quality


def exact_original_fragment(sequence, quality, originals):
    """Require both observed bases AND Phred string from one raw mate."""
    if not sequence or len(sequence) != len(quality):
        return False
    for raw, phred in originals:
        for orientation, scores in ((raw, phred),
                                    (raw.translate(_COMPLEMENT)[::-1], phred[::-1])):
            offset = orientation.find(sequence)
            while offset >= 0:
                if scores[offset:offset+len(sequence)] == quality:
                    return True
                offset = orientation.find(sequence, offset+1)
    return False


def attest(remap_csv, fastq_r1, fastq_r2):
    """Fail closed on missing raw names, altered rows, duplicates, or missing quality."""
    groups = defaultdict(list)
    with Path(remap_csv).open(newline="") as stream:
        for row in csv.DictReader(stream):
            name = row.get("qname")
            if not name:
                raise ValueError("Missing remap original pair ID")
            groups[name].append(row)
    if any(len(rows) != 2 for rows in groups.values()):
        raise ValueError("Expected two remap records per original read pair")
    total_original = 0
    matched_pairs = 0
    identical_remap_mate_sequences = 0
    identical_remap_mate_qualities = 0
    strict_phase_eligible_pair_rows = 0
    observed = set()
    for one, two in zip_longest(fastq(fastq_r1, 1), fastq(fastq_r2, 2)):
        if one is None or two is None or one[0] != two[0]:
            raise ValueError("Original FASTQ mate IDs/order disagree")
        name = one[0]
        if name in observed:
            raise ValueError("Duplicate original FASTQ pair ID")
        observed.add(name)
        total_original += 1
        rows = groups.pop(name, None)
        if rows is None:
            continue
        flags = {int(r["flag"]) & 0xC0 for r in rows}
        if flags != {0x40, 0x80}:
            raise ValueError("Remap lacks one original R1 and one R2 record")
        for row in rows:
            if not exact_original_fragment(row["seq"].upper(), row["qual"],
                                           ((one[1], one[2]), (two[1], two[2]))):
                raise ValueError("Remap sequence or quality not from original FASTQ")
        matched_pairs += 1
        identical_remap_mate_sequences += rows[0]["seq"] == rows[1]["seq"]
        identical_remap_mate_qualities += rows[0]["qual"] == rows[1]["qual"]
        strict_phase_eligible_pair_rows += _strict_pair(rows)
    if groups:
        raise ValueError("Remap pair IDs missing from original paired FASTQs")
    return {
        "schema_version": "ivanka.remap_original_fastq_provenance.v1",
        "raw_pair_ids_scanned": total_original,
        "remap_pair_ids_verified": matched_pairs,
        "remap_rows_verified": matched_pairs * 2,
        "identical_sequence_remap_mate_pairs": identical_remap_mate_sequences,
        "identical_quality_remap_mate_pairs": identical_remap_mate_qualities,
        "strict_proper_pair_ids_in_remap": strict_phase_eligible_pair_rows,
        "source_sha256": {
            "original_fastq_r1": digest(fastq_r1),
            "original_fastq_r2": digest(fastq_r2),
            "original_remap_csv": digest(remap_csv),
        },
        "all_remap_sequences_and_quality_from_raw_mates": True,
        "original_qname_pair_ids_verified": True,
        "independent_physical_molecules_inferred": False,
        "full_length_haplotype_phase_inferred": False,
        "read_or_consensus_files_modified": False,
        "interpretation": (
            "Every saved remap row's sequence AND quality substring was directly "
            "observed in one original FASTQ mate, possibly reverse complemented. "
            "The two SAM records of a pair may duplicate the same sequence and "
            "must not be counted as two physical molecules. This does not "
            "establish original PCR molecule independence, Q15 per-haplotype "
            "coverage, correct remap assignment, or full-length phase."),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("remap_csv", type=Path)
    parser.add_argument("original_r1_fastq", type=Path)
    parser.add_argument("original_r2_fastq", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = attest(args.remap_csv, args.original_r1_fastq,
                        args.original_r2_fastq)
        encoded = json.dumps(report, sort_keys=True, indent=2) + "\n"
        if args.output is not None:
            source = {p.resolve() for p in (args.remap_csv,
                      args.original_r1_fastq, args.original_r2_fastq)}
            destination = args.output.resolve()
            if destination in source:
                raise ValueError("Refusing to overwrite an original source")
            if destination.exists():
                if not destination.is_file() or destination.read_text() != encoded:
                    raise ValueError("Refusing to overwrite a different attestation")
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                handle = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(handle, "w") as stream:
                    stream.write(encoded)
        else:
            print(encoded)
    except (ValueError, KeyError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
