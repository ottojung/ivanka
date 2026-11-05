"""Direct Q15 allele-specific 31-mer evidence, read-pair deduplicated."""
from collections import Counter, defaultdict

_RC = str.maketrans("ACGT", "TGCA")


def reverse_complement(seq):
    return seq.translate(_RC)[::-1]


def _observed(mate, kmer, min_phred):
    sequence, qualities = mate
    for word in (kmer, reverse_complement(kmer)):
        start = 0
        while True:
            index = sequence.find(word, start)
            if index < 0:
                break
            if all(ord(q) - 33 >= min_phred
                   for q in qualities[index:index+len(word)]):
                return True
            start = index + 1
    return False


def observe_pair(candidate, mate1, mate2, min_phred):
    alt = candidate["context"][15:46]
    baseline = alt[:15] + candidate["reference"] + alt[16:]
    found_alt = any(_observed(mate, alt, min_phred)
                    for mate in (mate1, mate2))
    found_ref = any(_observed(mate, baseline, min_phred)
                    for mate in (mate1, mate2))
    if found_alt and found_ref:
        return "conflicting"
    return "alternative" if found_alt else "reference" if found_ref else "missing"


def summarized(candidate, observations, signatures, min_pairs):
    counts = Counter(observations)
    groups = defaultdict(set)
    for state, signature in zip(observations, signatures):
        groups[signature].add(state)
    unique = Counter(next(iter(states)) for states in groups.values()
                     if len(states) == 1)
    inconsistent_signature_groups = sum(len(states) > 1 for states in groups.values())
    unique_parent_offset = candidate["baseline_31mer_hits_in_parent"] == 1
    novel_alternative = candidate["alternative_31mer_hits_in_ordinary_fasta"] == 0
    qualified = (counts["alternative"] >= min_pairs
                 and unique["alternative"] >= min_pairs
                 and unique_parent_offset and novel_alternative)
    return {
        "parent_fasta_index": candidate["parent_fasta_index"],
        "snv_offset_zero_based": candidate["offset_zero_based"],
        "baseline_base": candidate["reference"],
        "alternate_base": candidate["alternative"],
        "assembled_record_support": candidate["assembled_record_support"],
        "sampled_31mer_witnesses": candidate["sampled_31mer_witnesses"],
        "reference_31mer_hits_in_own_parent":
            candidate["baseline_31mer_hits_in_parent"],
        "reference_31mer_hits_in_all_ordinary_contigs":
            candidate["baseline_31mer_hits_in_ordinary_fasta"],
        "alternative_31mer_hits_in_ordinary_contigs":
            candidate["alternative_31mer_hits_in_ordinary_fasta"],
        "exact_31mer_uniquely_locates_offset_in_parent": unique_parent_offset,
        "exact_31mer_uniquely_assigns_full_length_haplotype": False,
        "q15_original_pairs_observing_alternative": counts["alternative"],
        "q15_original_pairs_observing_reference": counts["reference"],
        "q15_original_pairs_with_both_alleles": counts["conflicting"],
        "q15_original_pairs_without_exact_31mer": counts["missing"],
        "q15_distinct_consistent_paired_sequences_alternative": unique["alternative"],
        "q15_distinct_consistent_paired_sequences_reference": unique["reference"],
        "paired_sequence_signatures_with_inconsistent_or_missing_observation":
            inconsistent_signature_groups,
        "candidate_meets_local_q15_screen": qualified,
        "locally_observed_not_haplotype_phased": True,
        "independent_physical_molecules_inferred": False,
    }
