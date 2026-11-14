use super::{Hits, Statistics, K};

/// Unique supported sequence, excluding every already-retained component.
pub(super) fn novel(
    i: usize,
    contigs: &[Vec<u8>],
    stats: &Statistics,
    hits: &Hits,
    picked: &[usize],
) -> usize {
    contigs[i]
        .windows(K)
        .enumerate()
        .filter(|(p, word)| {
            if stats.depth[i][*p] < 3 {
                return false;
            }
            let key: &[u8; K] = (*word).try_into().expect("fixed k-mer");
            hits.get(key).is_some_and(|locations| {
                locations.iter().any(|&(candidate, _)| candidate == i)
                    && locations
                        .iter()
                        .all(|&(candidate, _)| !picked.contains(&candidate))
            })
        })
        .count()
}
