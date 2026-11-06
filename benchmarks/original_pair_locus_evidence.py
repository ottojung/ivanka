"""Original read-pair Q15 co-observations at homologous UNPHASED loci."""
from collections import Counter, defaultdict
from itertools import combinations

from original_pair_locus_links import count_direct_links

from original_pair_phase_calls import pair_q15_calls
from original_pair_locus_groups import locus_groups
from snv_q15_fastq import iter_original_pairs


def evaluate_loci(contigs, r1, r2, *, max_pairs=1000, max_contigs=8,
                  short_flank=7, long_flank=15, min_alleles=5,
                  min_bridge_pairs=5, min_unique_signatures=3):
    if (type(max_pairs) is not int or not 1 <= max_pairs <= 50000
            or type(max_contigs) is not int or not 1 <= max_contigs <= 1000
            or any(type(x) is not int or x < 1 for x in
                   (min_alleles, min_bridge_pairs, min_unique_signatures))
            or not contigs):
        raise ValueError("Bounded direct original-pair research evidence required")
    index, positions, groups, scope = locus_groups(
        contigs, long_flank=long_flank, short_flank=short_flank)
    records = []
    calls_by_group = defaultdict(Counter)
    seen_ids = set()
    for name, mate1, mate2 in iter_original_pairs(r1, r2, max_pairs=max_pairs):
        if name in seen_ids:
            raise ValueError("Duplicate original paired read identifier")
        seen_ids.add(name)
        calls = pair_q15_calls(mate1, mate2, index, anchor=short_flank)
        records.append(((mate1[0], mate2[0]), calls))
        for gid, allele in calls.items():
            calls_by_group[gid][allele] += 1
    screened = contigs[:max_contigs]
    variants = []
    per_contig = []
    for ci, (header, seq) in enumerate(screened):
        sites = []
        for pos, base in enumerate(seq):
            gid = positions.get((ci, pos))
            counts = calls_by_group.get(gid, Counter())
            if (gid is not None and counts[base] >= min_alleles
                    and any(counts[a] >= min_alleles for a in "ACGT"
                            if a != base)):
                sites.append((pos, gid, base))
                variants.append(gid)
        per_contig.append((header, sites))
    unique_groups = set(variants)
    pair_counts, unique_counts = count_direct_links(records, unique_groups)
    # Report original read counts exactly ONCE per local equivalence group,
    # never in each competing full-length contig record.
    shared_loci = [
        {"group_sha256": groups[gid]["digest"],
         "distinct_member_contigs": len({
             ci for ci,_,_ in groups[gid]["members"]}),
         "q15_original_pair_allele_counts": dict(calls_by_group[gid])}
        for gid in sorted(unique_groups)]
    direct_links = [
        {"locus_group_sha256": [groups[a]["digest"], groups[b]["digest"]],
         "joint_original_pair_allele_combinations": {
             "".join(e): n for e,n in sorted(pair_counts[a,b].items())},
         "joint_distinct_consistent_pair_sequence_combinations": {
             "".join(e): n for e,n in sorted(unique_counts.get(
                 (a,b), Counter()).items())},
         "independent_original_dna_molecules": False}
        for a,b in sorted(pair_counts)]
    results = []
    for header, sites in per_contig:
        reports = []
        suspicious = []
        for (pa, ga, basea), (pb, gb, baseb) in combinations(sites, 2):
            if ga == gb:
                continue
            ordered = ga < gb
            key = (ga, gb) if ordered else (gb, ga)
            expected = (basea, baseb) if ordered else (baseb, basea)
            counts = pair_counts[key]
            unique = unique_counts.get(key, Counter())
            supported_other = [
                {"alleles": list(event), "original_pairs": count,
                 "consistent_paired_sequence_signatures": unique[event]}
                for event, count in sorted(counts.items())
                if event != expected and count >= min_bridge_pairs
                and unique[event] >= min_unique_signatures]
            contradicted = counts[expected] == 0 and bool(supported_other)
            if contradicted:
                suspicious.append([pa, pb])
            reports.append({
                "positions_zero_based": [pa,pb],
                "equivalent_locus_group_sha256": [
                    groups[ga]["digest"], groups[gb]["digest"]],
                "contig_alleles": [basea,baseb],
                "source_locus_evidence_is_global_not_per_contig": True,
                "candidate_allele_observed_directly": counts[expected] > 0,
                "other_direct_combination_exceeds_threshold":
                    bool(supported_other),
                "direct_local_conflict_flag": contradicted,
                "unobserved_phase_is_unknown": True,
                "not_a_full_length_haplotype_phase_claim": True,
            })
        results.append({
            "contig": header,
            "qualifying_locus_sites": [
                {"position_zero_based": pos,
                 "equivalence_group_sha256": groups[gid]["digest"],
                 "group_member_contigs": len({
                     ci for ci,_,_ in groups[gid]["members"]}),
                 "base": base,
                 "read_support_must_be_looked_up_once_in_shared_loci": True}
                for pos,gid,base in sites],
            "direct_candidate_locus_pairs": reports,
            "tentative_conflict_positions": suspicious,
            "delete_or_filter_contig": False,
        })
    return {
        "schema_version": "ivanka.original_pair_homologous_unphased_loci.v1",
        "source_contig_scope": scope,
        "original_read_pairs_scanned": len(records),
        "minimum_phred_each_observed_context_base": 15,
        "exact_original_paired_id_deduplicated": True,
        "overlapping_mate_allele_conflicts_excluded": True,
        "unique_local_variant_groups_screened": len(unique_groups),
        "unique_shared_locus_evidence": shared_loci,
        "unique_direct_original_pair_link_evidence": direct_links,
        "results": results,
        "original_pairs_not_multiplied_across_equivalent_contigs": True,
        "full_length_haplotype_phase_inferred": False,
        "independent_physical_molecules_inferred": False,
        "may_modify_micall_max_or_fasta": False,
        "may_delete_contigs": False,
        "interpretation": ("Potential homologous-locus alleles and direct "
          "paired-read co-observations only; same long local flanks do NOT "
          "prove a shared biological locus in different haplotypes. "
          "No original reads assigned to one competing full-length contig."),
    }
