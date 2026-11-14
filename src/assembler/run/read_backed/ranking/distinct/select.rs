use super::novelty::novel;
use super::{Hits, Statistics};
use std::cmp::Reverse;

/// Keep independent read-backed fragments separate; never fabricate their join.
pub(crate) fn complements(
    contigs: &[Vec<u8>],
    stats: &Statistics,
    hits: &Hits,
    primary: usize,
) -> Vec<usize> {
    let mut picked = vec![primary];
    while picked.len() < 8 {
        let next = (0..contigs.len())
            .filter_map(|i| {
                if picked.contains(&i) || stats.coverage[i] == 0 {
                    return None;
                }
                let independent = novel(i, contigs, stats, hits, &picked);
                (independent * 2 >= stats.coverage[i] && independent * 5 >= stats.coverage[primary])
                    .then_some((i, independent))
            })
            .max_by_key(|&(i, independent)| (independent, stats.pairs[i], Reverse(i)));
        match next {
            Some((i, _)) => picked.push(i),
            None => break,
        }
    }
    picked.remove(0);
    picked
}

/// Preserve the single-complement selection contract for focused tests.
#[cfg(test)]
pub(crate) fn complement(
    contigs: &[Vec<u8>],
    stats: &Statistics,
    hits: &Hits,
    primary: usize,
) -> Option<usize> {
    complements(contigs, stats, hits, primary)
        .into_iter()
        .next()
}
