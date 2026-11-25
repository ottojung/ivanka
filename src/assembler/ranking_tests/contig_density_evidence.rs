use super::*;
use std::collections::HashMap;

fn path(seed: u64, len: usize) -> Vec<u8> {
    let mut x = seed;
    (0..len)
        .map(|_| {
            x ^= x << 13;
            x ^= x >> 7;
            x ^= x << 17;
            b"ACGT"[(x & 3) as usize]
        })
        .collect()
}

// Rejecting a short near-duplicate must not destroy its read evidence: with
// the sampled read-kmer map supplied, it is recorded as unphased SNV support.
#[test]
fn short_single_snv_neighbour_keeps_read_evidence_in_audit() {
    let major = path(0x1234_5678_9abc_def0, 310);
    let mut minor = major.clone();
    minor[155] = if minor[155] == b'A' { b'C' } else { b'A' };
    let mut sampled = HashMap::new();
    for k in minor.windows(K).filter_map(ranking::canonical_kmer) {
        sampled.insert(k, 10);
    }
    let (kept, audit) =
        select_supported_contigs_with_kmers(vec![major, minor], vec![300, 150], 16, 0, &sampled);
    assert_eq!((kept.len(), audit.len()), (1, 1));
}

// Two linked substitutions within one k-mer span encode a phased haplotype,
// not an isolated unphased SNV. Preserve both when read support is abundant.
#[test]
fn short_linked_two_snv_minority_must_remain_phased() {
    let major = path(0xabc0_1234_5678_9def, 310);
    let mut minor = major.clone();
    for pos in [20, 21] {
        minor[pos] = if minor[pos] == 65 { 67 } else { 65 };
    }
    let mut sampled = HashMap::new();
    for k in minor.windows(K).filter_map(ranking::canonical_kmer) {
        sampled.insert(k, 30);
    }
    let (kept, _) =
        select_supported_contigs_with_kmers(vec![major, minor], vec![300, 90], 16, 0, &sampled);
    assert_eq!(kept.len(), 2, "linked minority haplotype was collapsed");
}
