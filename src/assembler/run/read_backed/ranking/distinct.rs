use super::{Hits, Statistics, K};
use std::cmp::Reverse;
use std::collections::HashSet;

/// Select one more read-supported component whose k-mers are largely absent
/// from every component already retained.
pub(crate) fn distinct(
    contigs: &[Vec<u8>],
    stats: &Statistics,
    hits: &Hits,
    selected: &[usize],
) -> Option<usize> {
    let selected_set: HashSet<usize> = selected.iter().copied().collect();
    let max_coverage = selected
        .iter()
        .map(|&i| stats.coverage[i])
        .max()
        .unwrap_or(0)
        .max(1);
    (0..contigs.len())
        .filter(|index| !selected_set.contains(index))
        .filter_map(|index| {
            let novel = contigs[index]
                .windows(K)
                .enumerate()
                .filter(|(position, window)| {
                    if stats.depth[index][*position] < 3 {
                        return false;
                    }
                    let key: &[u8; K] = (*window).try_into().expect("fixed window");
                    hits.get(key).is_some_and(|loci| {
                        loci.iter().any(|&(candidate, _)| candidate == index)
                            && loci
                                .iter()
                                .all(|&(candidate, _)| !selected_set.contains(&candidate))
                    })
                })
                .count();
            (stats.coverage[index] > 0
                && novel * 2 >= stats.coverage[index]
                && novel * 5 >= max_coverage)
                .then_some((index, novel))
        })
        .max_by_key(|&(index, novel)| (novel, stats.pairs[index], Reverse(index)))
        .map(|(index, _)| index)
}
