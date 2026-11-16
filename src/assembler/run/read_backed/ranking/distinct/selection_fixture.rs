use super::{PairLinks, Statistics, K};

fn dna(len: usize, seed: u64) -> Vec<u8> {
    let mut x = seed;
    (0..len)
        .map(|_| {
            x ^= x << 13;
            x ^= x >> 7;
            x ^= x << 17;
            b"ACGT"[(x % 4) as usize]
        })
        .collect()
}

pub(super) fn fixture() -> (Vec<Vec<u8>>, Statistics, PairLinks) {
    let mut alternate = dna(1_025, 17);
    for position in (45..995).step_by(50) {
        alternate[position] = if alternate[position] == b'A' {
            b'C'
        } else {
            b'A'
        };
    }
    let contigs = vec![dna(1_000, 17), alternate];
    let depth = contigs.iter().map(|s| vec![7; s.len() - K + 1]).collect();
    let stats = Statistics {
        depth,
        pairs: vec![8_000, 6_000],
        coverage: vec![1_000 - K + 1, 1_025 - K + 1],
    };
    let links = [
        ((0, 0), 8_000),
        ((1, 1), 6_000),
        ((0, 1), 5_200),
        ((1, 0), 5_100),
    ]
    .into_iter()
    .collect();
    (contigs, stats, links)
}
