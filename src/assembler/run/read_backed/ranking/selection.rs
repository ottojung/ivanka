//! Preserve separate read-supported DNA components; never consult references.
use super::{rolling_canonical_kmers, Statistics};
use std::collections::HashSet;

pub(crate) fn supported_components(contigs: &[Vec<u8>], stats: &Statistics) -> Vec<usize> {
    let primary = super::best(contigs, stats);
    let mut marked: HashSet<u64> = rolling_canonical_kmers(&contigs[primary]).collect();
    let mut kept = vec![primary];
    let mut rest = (0..contigs.len())
        .filter(|&i| i != primary)
        .collect::<Vec<_>>();
    rest.sort_unstable_by_key(|&i| {
        (
            std::cmp::Reverse((stats.coverage[i] as u128) * (stats.pairs[i] as u128)),
            i,
        )
    });
    for i in rest {
        // Require both broad 31-mer evidence and many independent original
        // pairs. An unsupported fragment does not become a second contig.
        if stats.coverage[i] < 128
            || stats.pairs[i] < 128
            || (stats.pairs[i] as u128) * 8 < stats.pairs[primary] as u128
        {
            continue;
        }
        let observed = rolling_canonical_kmers(&contigs[i]).collect::<HashSet<_>>();
        let unseen = observed.iter().filter(|key| !marked.contains(key)).count();
        if observed.len() < 128 || unseen * 4 < observed.len() * 3 {
            continue;
        }
        kept.push(i);
        marked.extend(observed);
        if kept.len() == 16 {
            break;
        }
    }
    kept
}
