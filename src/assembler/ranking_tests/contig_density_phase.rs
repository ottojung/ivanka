use super::*;
use std::collections::HashMap;

// Linked distant substitutions remain one phased minority molecule, not
// two unphased single-site observations, at the 15% abundance boundary.
#[test]
fn distant_linked_snv_minority_survives_exact_redundancy() {
    let major: Vec<u8> = (0..310).map(|i| b"ACGT"[(i * 17 + i / 7) % 4]).collect();
    let mut minor = major.clone();
    for pos in [40, 260] {
        minor[pos] = if minor[pos] == b"A"[0] {
            b"C"[0]
        } else {
            b"A"[0]
        };
    }
    let sampled: HashMap<u64, u32> = minor
        .windows(K)
        .filter_map(ranking::canonical_kmer)
        .map(|k| (k, 15))
        .collect();
    let (kept, audit) = select_supported_contigs_with_kmers(
        vec![major, minor.clone()],
        vec![850, 150],
        16,
        0,
        &sampled,
    );
    assert_eq!(kept.len(), 2, "15% phased minority was discarded");
    assert!(kept.contains(&minor));
    assert!(audit.is_empty());
}
