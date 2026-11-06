"""Homologous local-locus groups: shared reads are NOT full-contig reads.

Identical long flanks in multiple contigs define a possible local locus
equivalence class. Every observed shorter allele context must point to only
one group across the entire reference collection; ambiguous groups vanish.
"""
import hashlib
from collections import Counter, defaultdict

from snv_q15_evidence import reverse_complement


def locus_groups(contigs, *, long_flank=15, short_flank=7):
    if (type(long_flank) is not int or type(short_flank) is not int
            or not 5 <= short_flank < long_flank <= 50):
        raise ValueError("Expected strict short/long flank bounds")
    entries = defaultdict(list)
    for ci, (_, seq) in enumerate(contigs):
        if not seq or set(seq) - set("ACGT"):
            raise ValueError("Only resolved A/C/G/T contigs may define groups")
        for pos in range(long_flank, len(seq)-long_flank):
            key = (seq[pos-long_flank:pos],
                   seq[pos+1:pos+long_flank+1])
            entries[key].append((ci, pos, seq[pos]))
    keys = sorted(entries)
    # One long-flank site per contig: within-contig repeats are unsafe.
    repeated = {key for key, sites in entries.items()
                if max(Counter(ci for ci, _, _ in sites).values()) > 1}
    owners = defaultdict(set)
    tokens = {}
    ambiguous_alleles = set()
    for gi, key in enumerate(keys):
        left, right = key[0][-short_flank:], key[1][:short_flank]
        contexts = set()
        for allele in "ACGT":
            word = left + allele + right
            for token in (word, reverse_complement(word)):
                owners[token].add(gi)
                contexts.add((token, allele))
        tokens[gi] = contexts
        by_word = defaultdict(set)
        for word, allele in contexts:
            by_word[word].add(allele)
        if any(len(alleles) != 1 for alleles in by_word.values()):
            ambiguous_alleles.add(gi)
    viable = {}
    for gi, key in enumerate(keys):
        if (key not in repeated and gi not in ambiguous_alleles and all(
                owners[word] == {gi} for word, _ in tokens[gi])):
            viable[gi] = key
    index = {}
    positions = {}
    groups = {}
    for gi, key in viable.items():
        for token, allele in tokens[gi]:
            index[token] = (gi, allele)
        for ci, pos, base in entries[key]:
            positions[ci, pos] = gi
        groups[gi] = {
            "digest": hashlib.sha256((key[0]+"|"+key[1]).encode()).hexdigest(),
            "members": tuple(entries[key]),
        }
    return index, positions, groups, {
        "long_flank": long_flank,
        "short_flank": short_flank,
        "all_candidate_locus_groups": len(entries),
        "admissible_unique_locus_groups": len(viable),
        "excluded_ambiguous_or_repeated_groups": len(entries)-len(viable),
        "scope_all_original_contigs": len(contigs),
        "full_contig_read_coverage_assigned": False,
    }
