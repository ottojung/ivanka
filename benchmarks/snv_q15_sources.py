"""Independently pinned exact sources and safe local SNV-to-FASTA binding."""
import csv
import hashlib
from pathlib import Path
from snv_q15_evidence import reverse_complement

_META = (
    "#schema=ivanka.unphased_snv_candidates.v1",
    "#phasing=unidentified; independent_dna_molecules=false",
    "#sampling=first_50000_pairs_every_third_31mer; kmer_counts_are_occurrences_not_molecules; phred_unchecked=true",
    "#ordinary_micall_fasta_unchanged=true",
)
_FIELDS = ("parent_fasta_index", "length", "snv_offset_zero_based",
           "baseline_base", "alternate_base", "assembling_read_record_support",
           "novel_sampled_31mers_ge5", "local_61base_unphased_context")


def verify_source(path, expected):
    if not isinstance(expected, str) or len(expected) != 64 or any(
            c not in "0123456789abcdef" for c in expected):
        raise ValueError("Expected an externally pinned lowercase SHA256")
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ValueError("External source SHA256 mismatch")
    return expected


def fasta_records(path):
    records = []
    sequence = None
    declared_length = None
    with Path(path).open() as stream:
        for line in stream:
            value = line.strip()
            if value.startswith(">"):
                if sequence is not None:
                    joined = "".join(sequence).upper()
                    if len(joined) != declared_length:
                        raise ValueError("FASTA declared length disagrees with sequence")
                    records.append(joined)
                prefix = f">ivanka_{len(records)+1} len="
                if not value.startswith(prefix):
                    raise ValueError("FASTA contig ordering or header malformed")
                declared_length = int(value[len(prefix):])
                if declared_length < 1:
                    raise ValueError("Invalid FASTA length")
                sequence = []
            elif value:
                if sequence is None:
                    raise ValueError("FASTA data without header")
                sequence.append(value)
    if sequence is not None:
        joined = "".join(sequence).upper()
        if len(joined) != declared_length:
            raise ValueError("FASTA declared length disagrees with sequence")
        records.append(joined)
    return records


def _exact_oriented_hits(sequence, kmer):
    """Count all overlapping 31-mer starts, on either strand just once."""
    total = 0
    for pattern in {kmer, reverse_complement(kmer)}:
        start = 0
        while True:
            start = sequence.find(pattern, start)
            if start < 0:
                break
            total += 1
            start += 1
    return total


def bound_candidates(tsv, fasta):
    ordinary = fasta_records(fasta)
    with Path(tsv).open(newline="") as stream:
        meta = tuple(stream.readline().rstrip("\n") for _ in range(4))
        if meta != _META:
            raise ValueError("Audit must be explicitly unphased and unqualified")
        reader = csv.DictReader(stream, delimiter="\t")
        if tuple(reader.fieldnames or ()) != _FIELDS:
            raise ValueError("Unsupported SNV TSV schema")
        rows = list(reader)
    if len(rows) > 16:
        raise ValueError("Overlong local SNV audit")
    candidates = []
    observed = set()
    for row in rows:
        parent_index = int(row["parent_fasta_index"])
        pos = int(row["snv_offset_zero_based"])
        if not 1 <= parent_index <= len(ordinary):
            raise ValueError("SNV references an absent ordinary FASTA contig")
        original = ordinary[parent_index-1]
        alt = row["alternate_base"]
        base = row["baseline_base"]
        context = row["local_61base_unphased_context"]
        if (len(context) != 61 or set(context) - set("ACGT")
                or len(alt) != 1 or len(base) != 1 or alt == base
                or not 30 <= pos < len(original)-30
                or len(original) != int(row["length"])
                or original[pos] != base
                or context[:30] != original[pos-30:pos]
                or context[30] != alt
                or context[31:] != original[pos+1:pos+31]
                or int(row["assembling_read_record_support"]) < 50
                or int(row["novel_sampled_31mers_ge5"]) < 3):
            raise ValueError("SNV does not match original FASTA local context")
        marker = (parent_index, pos, alt)
        if marker in observed:
            raise ValueError("Duplicate reported SNV")
        observed.add(marker)
        alt_31 = context[15:46]
        ref_31 = alt_31[:15] + base + alt_31[16:]
        parent_hits = _exact_oriented_hits(original, ref_31)
        global_hits = sum(_exact_oriented_hits(seq, ref_31) for seq in ordinary)
        alt_in_contigs = sum(_exact_oriented_hits(seq, alt_31) for seq in ordinary)
        candidates.append({"parent_fasta_index": parent_index,
                           "baseline_31mer_hits_in_parent": parent_hits,
                           "baseline_31mer_hits_in_ordinary_fasta": global_hits,
                           "alternative_31mer_hits_in_ordinary_fasta": alt_in_contigs,
                           "offset_zero_based": pos, "reference": base,
                           "alternative": alt, "context": context,
                           "assembled_record_support":
                               int(row["assembling_read_record_support"]),
                           "sampled_31mer_witnesses":
                               int(row["novel_sampled_31mers_ge5"])})
    return candidates
