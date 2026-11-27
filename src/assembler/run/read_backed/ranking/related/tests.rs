pub(super) use super::{additional, counts, Statistics};

mod cases;
mod controls;

fn stats(coverage: Vec<usize>, masks: Vec<u16>, exclusive: Vec<u16>) -> Statistics {
    let pairs = (0..coverage.len())
        .map(|i| masks.iter().filter(|&&m| m & (1 << i) != 0).count())
        .collect();
    let spans = vec![vec![]; coverage.len()];
    Statistics {
        depth: vec![vec![3; 2000]; coverage.len()],
        pairs,
        coverage,
        pair_masks: masks,
        exclusive_masks: exclusive,
        spans,
    }
}

fn long_contigs(n: usize) -> Vec<Vec<u8>> {
    (0..n).map(|_| vec![b'A'; 2000]).collect()
}
