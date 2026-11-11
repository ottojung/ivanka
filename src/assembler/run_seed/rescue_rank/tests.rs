use super::*;
#[test]
fn rescue_replaces_only_redundant_unprotected_contig() {
    let mut old = vec![vec![b'A'; 80], vec![b'A'; 100], vec![b'C'; 90]];
    let rescue = vec![b'G'; 1200];
    assert!(append_preserving_diversity(&mut old, rescue, 3, 1));
    assert_eq!(old[0], vec![b'A'; 80]);
    assert_eq!(old.iter().map(Vec::len).max(), Some(1200));
}

#[test]
fn distinct_contigs_are_never_displaced() {
    let mut old = vec![vec![b'A'; 80], vec![b'C'; 80]];
    assert!(!append_preserving_diversity(
        &mut old,
        b"ACGT".repeat(300),
        2,
        0
    ));
    assert_eq!(old.len(), 2);
}

#[test]
fn accepted_rescue_preserves_canonical_kmer_union() {
    let mut old = vec![vec![b'A'; 80], vec![b'A'; 100], vec![b'C'; 90]];
    let kmers = |v: &[Vec<u8>]| -> HashSet<u64> {
        v.iter().flat_map(|s| rolling_canonical_kmers(s)).collect()
    };
    let before = kmers(&old);
    assert!(append_preserving_diversity(
        &mut old,
        vec![b'G'; 1200],
        3,
        1
    ));
    assert!(before.is_subset(&kmers(&old)));
}
