use super::{index, ranking, scoring};

pub(super) fn random_sequence(mut seed: u32, size: usize) -> Vec<u8> {
    (0..size)
        .map(|_| {
            seed ^= seed << 13;
            seed ^= seed >> 17;
            seed ^= seed << 5;
            b"ACGT"[(seed as usize) & 3]
        })
        .collect()
}

pub(super) fn choose(contigs: &[Vec<u8>]) -> Option<usize> {
    let hits = index::build(contigs);
    let depths = contigs.iter().map(|s| vec![4; s.len() - 30]).collect();
    let stats = scoring::Statistics {
        depth: depths,
        pairs: vec![50; contigs.len()],
        coverage: contigs.iter().map(|s| s.len() - 30).collect(),
    };
    ranking::complement(contigs, &stats, &hits, 0)
}

#[test]
fn retains_independent_supported_components() {
    let contigs = vec![random_sequence(42, 2400), random_sequence(7, 1850)];
    assert_eq!(choose(&contigs), Some(1));
}

#[test]
fn rejects_almost_duplicate_haplotype() {
    let original = random_sequence(42, 2400);
    let mut alternate = original.clone();
    for index in [70, 290, 1200, 2050] {
        alternate[index] = if alternate[index] == b'A' { b'C' } else { b'A' };
    }
    assert_eq!(choose(&[original, alternate]), None);
}
