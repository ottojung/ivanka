use super::*;

#[test]
fn supported_single_snv_haplotype_is_not_kmer_redundant() {
    let mut x = 0x9e3779b97f4a7c15u64;
    let major = (0..900)
        .map(|_| {
            x ^= x << 13;
            x ^= x >> 7;
            x ^= x << 17;
            b"ACGT"[(x & 3) as usize]
        })
        .collect::<Vec<_>>();
    let mut minor = major.clone();
    minor[450] = if minor[450] == b'A' { b'C' } else { b'A' };
    let mut sampled = std::collections::HashMap::new();
    for k in minor.windows(K).filter_map(super::ranking::canonical_kmer) {
        sampled.insert(k, 10);
    }
    let (kept, audit) =
        select_supported_contigs_with_kmers(vec![major, minor], vec![300, 150], 16, 0, &sampled);
    assert_eq!(
        (kept.len(), audit.len()),
        (1, 1),
        "MiCall unchanged; separate SNV evidence"
    );
}
