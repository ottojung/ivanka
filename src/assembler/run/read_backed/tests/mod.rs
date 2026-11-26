use super::{index, island, output, ranking, scoring, tiling, trimming, Reads, K};
mod independent_cases;
mod junction_cases;
mod junction_output_cases;
mod pair_masks;
mod private_branch_cases;
mod private_evidence_cases;
mod ranking_cases;
mod tiling_cases;
mod trimming_cases;

fn private_stats(coverage: Vec<usize>, depth: Vec<Vec<u32>>) -> scoring::Statistics {
    let masks = [vec![3u16; 700], vec![2; 300]].concat();
    let pairs = (0..2)
        .map(|i| masks.iter().filter(|&&m| m & (1 << i) != 0).count())
        .collect();
    let spans = vec![vec![]; coverage.len()];
    scoring::Statistics {
        depth,
        pairs,
        coverage,
        pair_masks: masks,
        spans,
    }
}

fn private_depth(seq: &[u8], supported: bool) -> Vec<u32> {
    vec![if supported { 3 } else { 0 }; seq.len().saturating_sub(K - 1)]
}

fn primary() -> Vec<u8> {
    vec![b'A'; 4000]
}

fn branch(private_bases: usize) -> Vec<u8> {
    let mut seq = vec![b'A'; 4000 - private_bases];
    seq.extend(vec![b'G'; private_bases]);
    seq
}

fn reverse(seq: &[u8]) -> Vec<u8> {
    seq.iter()
        .rev()
        .map(|&b| match b {
            b'A' => b'T',
            b'C' => b'G',
            b'G' => b'C',
            _ => b'A',
        })
        .collect()
}

/// Dense flanking pair evidence with no fragment spanning the middle valley.
pub(super) fn dense_spans() -> Vec<(usize, usize)> {
    [vec![(500, 650); 100], vec![(1840, 1970); 100]].concat()
}
