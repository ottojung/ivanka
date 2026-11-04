"""Read-backed pairwise-variant phase support, using exact local anchors.

Only reference-specific local observations and original R1/R2 pairs are
considered. Never infer insert bases, assign physical molecule independence,
or claim phase beyond two explicitly specified sites. Not a clinical model.
"""
import argparse
from collections import Counter, defaultdict
import gzip
import json
from pathlib import Path

from synthetic_phase_pairs import reverse_complement
from synthetic_phase_fidelity import anchored_allele, fasta_records


def _records(path):
    op = gzip.open if str(path).endswith(".gz") else open
    with op(path, "rt") as stream:
        while (header := stream.readline()):
            seq, plus, qual = (stream.readline() for _ in range(3))
            if (not header.startswith("@") or not plus.startswith("+")
                    or not seq or not qual
                    or len(seq.rstrip("\r\n")) != len(qual.rstrip("\r\n"))):
                raise ValueError("Malformed paired FASTQ record")
            yield (header.rstrip("\r\n"), seq.rstrip("\r\n").upper(),
                   qual.rstrip("\r\n"))


def _call(read, qualities, reference, position, anchor, minimum_quality):
    """Q15 (or requested quality) exact local flanks; no insert imputation."""
    left = reference[position-anchor:position]
    right = reference[position+1:position+1+anchor]
    observed = set()
    for oriented, qvals in ((read, qualities),
                            (reverse_complement(read), qualities[::-1])):
        for base in "ACGT":
            motif = left + base + right
            start = oriented.find(motif)
            if (start >= 0 and oriented.find(motif, start+1) < 0
                    and all(ord(c)-33 >= minimum_quality
                            for c in qvals[start:start+len(motif)])):
                observed.add(base)
    return next(iter(observed)) if len(observed) == 1 else None


def _id(header, mate):
    words = header.split()
    if (len(words) != 2 or not words[0].startswith("@")
            or not words[1].startswith(str(mate) + ":")):
        raise ValueError("Missing or invalid original FASTQ mate identifier")
    return words[0][1:]


def audit_pairwise_phase(r1, r2, reference, positions, contigs,
                         anchor=25, minimum_bridges=3, minimum_quality=15):
    """No real haplotype labels are used: only original paired read observations."""
    if (len(positions) != 2 or positions[0] >= positions[1]
            or anchor < 1 or minimum_bridges < 1 or minimum_quality < 0
            or positions[0] < anchor or positions[1] + anchor >= len(reference)):
        raise ValueError("Invalid phase sites or anchor geometry")
    spectrum, sig_observations = Counter(), defaultdict(set)
    pair_count = 0
    names = set()
    r1_iter, r2_iter = _records(r1), _records(r2)
    sentinel = object()
    from itertools import zip_longest
    for a, b in zip_longest(r1_iter, r2_iter, fillvalue=sentinel):
        if a is sentinel or b is sentinel:
            raise ValueError("FASTQ mate count disagreement")
        name1, name2 = _id(a[0], 1), _id(b[0], 2)
        if name1 != name2:
            raise ValueError("FASTQ original pair identifiers disagree")
        if name1 in names:
            raise ValueError("Duplicate original paired FASTQ identifier")
        names.add(name1)
        pair_count += 1
        calls = []
        for pos in positions:
            observed = {base for read, qual in ((a[1], a[2]), (b[1], b[2]))
                        if (base := _call(read, qual, reference, pos,
                                          anchor, minimum_quality)) is not None}
            calls.append(next(iter(observed)) if len(observed) == 1 else None)
        phase = tuple(calls) if all(x is not None for x in calls) else None
        if phase is not None:
            spectrum[phase] += 1
        sig_observations[(a[1], b[1])].add(phase)
    distinct = Counter()
    for observed in sig_observations.values():
        if len(observed) == 1 and None not in observed:
            distinct[next(iter(observed))] += 1
    phase_evidence = [
        {"allele_pair": list(pair), "original_qname_pairs": count,
         "distinct_consistent_read_pair_sequences": distinct[pair]}
        for pair, count in sorted(spectrum.items())
    ]
    total_direct = sum(spectrum.values())
    out = []
    for header, sequence in contigs:
        orientations = []
        for label, path in (("+", sequence), ("-", reverse_complement(sequence))):
            calls = tuple(anchored_allele(path, reference, p, anchor)
                          for p in positions)
            if all(x is not None for x in calls):
                orientations.append((label, calls))
        if len(orientations) != 1:
            label, calls, status = None, (None, None), "unresolved_or_ambiguous"
        else:
            label, calls = orientations[0]
            if total_direct < minimum_bridges:
                status = "not_identifiable_from_direct_pairs"
            elif spectrum[calls] == 0:
                status = "unsupported_by_observed_direct_pair_phase"
            else:
                status = "observed_direct_pair_phase"
        out.append({"contig": header, "orientation": label,
                    "allele_calls": list(calls), "classification": status,
                    "supporting_original_pair_ids": spectrum[calls]})
    return {
        "original_pair_ids_read": pair_count,
        "original_pair_ids_sequencing_both_sites": total_direct,
        "phase_observations": phase_evidence,
        "minimum_direct_pair_ids_for_assessment": minimum_bridges,
        "minimum_phred_per_exact_anchor_base": minimum_quality,
        "contigs": out,
        "independent_physical_molecules_inferred": False,
        "phase_beyond_two_selected_sites_inferred": False,
        "interpretation": (
            "Counts of directly observed Q15-filtered original paired-read "
            "local anchors, not independent physical molecules. The absence "
            "of an observed phase from sufficiently many directly bridging "
            "pairs is a warning, not proof a rare haplotype is impossible. "
            "A matching local phase is not proof of whole-genome phasing."),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("r1", type=Path)
    parser.add_argument("r2", type=Path)
    parser.add_argument("reference_fasta", type=Path)
    parser.add_argument("assembled_fasta", type=Path)
    parser.add_argument("--sites", nargs=2, type=int, required=True)
    parser.add_argument("--anchor", type=int, default=25)
    parser.add_argument("--min-phred", type=int, default=15)
    args = parser.parse_args()
    reference = fasta_records(args.reference_fasta)
    if len(reference) != 1:
        parser.error("Expected one synthetic reference sequence")
    result = audit_pairwise_phase(
        args.r1, args.r2, reference[0][1], args.sites,
        fasta_records(args.assembled_fasta), args.anchor,
        minimum_quality=args.min_phred)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
