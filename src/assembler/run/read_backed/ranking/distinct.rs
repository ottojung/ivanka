use super::{Hits, Statistics, K};
use std::cmp::Reverse;

/// A second component is useful only when its own read-backed k-mers
/// mostly describe sequence absent from the primary path, in either strand.
pub(crate) fn complement(
    contigs: &[Vec<u8>],
    stats: &Statistics,
    hits: &Hits,
    primary: usize,
) -> Option<usize> {
    (0..contigs.len())
        .filter_map(|i| {
            let novel = contigs[i]
                .windows(K)
                .enumerate()
                .filter(|(p, window)| {
                    if stats.depth[i][*p] < 3 {
                        return false;
                    }
                    let key: &[u8; K] = (*window).try_into().expect("fixed window");
                    hits.get(key).is_some_and(|loci| {
                        loci.iter().any(|&(candidate, _)| candidate == i)
                            && loci.iter().all(|&(candidate, _)| candidate != primary)
                    })
                })
                .count();
            (i != primary
                && stats.coverage[i] > 0
                && novel * 2 >= stats.coverage[i]
                && novel * 5 >= stats.coverage[primary])
                .then_some((i, novel))
        })
        .max_by_key(|&(i, novel)| (novel, stats.pairs[i], Reverse(i)))
        .map(|(i, _)| i)
}
