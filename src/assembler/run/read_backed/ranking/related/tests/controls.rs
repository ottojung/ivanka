use super::{additional, counts, long_contigs, stats};

#[test]
fn clonal_duplicate_without_discriminating_pairs_is_not_added() {
    // A clone has no exclusive 31-mers at all: the related path must not
    // manufacture a second phase from shared read evidence.
    let evidence = stats(vec![1990, 1990], vec![3; 2000], vec![0; 2000]);
    assert!(additional(&long_contigs(2), &evidence, 0).is_empty());
}

#[test]
fn shared_discriminating_fragments_cannot_establish_two_phases() {
    // One pair carries exclusive loci for BOTH candidates 1 and 2 (mask 6).
    // After candidate 1 consumes those pairs, candidate 2 has no remaining
    // independent evidence: a fragment cannot vote twice for two phases.
    let evidence = stats(vec![1990, 1990, 1990], vec![7; 2000], vec![6; 2000]);
    assert_eq!(additional(&long_contigs(3), &evidence, 0), vec![1]);
}

#[test]
fn gapped_related_candidate_is_not_added() {
    // A wide evidence hole would fragment the candidate into tiles; those
    // fragments cannot establish one phase-contiguous haplotype.
    let mut evidence = stats(vec![1990, 1990], vec![3; 2000], vec![2; 1200]);
    evidence.depth[1][900..1300].fill(0);
    assert!(additional(&long_contigs(2), &evidence, 0).is_empty());
}

#[test]
fn exclusive_pair_counts_honor_sixteen_candidate_bound_and_selected_mask() {
    // The mask is u16: 16 candidates is the maximum. Mixed bits are counted
    // once per candidate, and any pair already explained by the selected
    // component is skipped so a second phase cannot reuse its evidence.
    let masks = vec![0xfffeu16, 0x0002, 0x0006, 0x0000];
    let fresh = counts(&masks, 1, 16);
    assert_eq!((fresh[0], fresh[1], fresh[2], fresh[15]), (0, 3, 2, 1));
    let consumed = counts(&masks, 3, 16);
    assert_eq!((consumed[1], consumed[2], consumed[15]), (0, 0, 0));
    let partial = counts(&masks, 5, 16);
    assert_eq!((partial[1], partial[2]), (1, 0));
}
