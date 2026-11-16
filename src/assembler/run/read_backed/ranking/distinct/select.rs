use super::{mate_linked, novelty::novel, redundant::not_independent};
use super::{Hits, PairLinks, Statistics};
use std::cmp::Reverse;

/// Keep independent read-backed fragments separate; never fabricate their join.
pub(crate) fn complements(
    contigs: &[Vec<u8>],
    stats: &Statistics,
    hits: &Hits,
    primary: usize,
    links: &PairLinks,
) -> Vec<usize> {
    let mut picked = vec![primary];
    while picked.len() < 8 {
        let next = (0..contigs.len())
            .filter_map(|i| {
                if picked.contains(&i)
                    || stats.coverage[i] == 0
                    || !mate_linked(i, &picked, links)
                    || picked
                        .iter()
                        .any(|&j| not_independent(i, j, contigs, links, stats))
                {
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
    let links = (0..contigs.len())
        .map(|i| ((i, i), 3))
        .collect::<PairLinks>();
    complements(contigs, stats, hits, primary, &links)
        .into_iter()
        .next()
}
