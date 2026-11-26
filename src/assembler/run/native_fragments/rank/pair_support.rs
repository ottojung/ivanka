use super::mates::identity;
use super::{rolling_canonical_kmers, Reads};
use std::collections::{HashMap, HashSet};

type Counts<'a> = HashMap<&'a [u8], (&'a [u8], usize)>;

/// Count identities from distinct observed pairs; equal-mate pairs vote once.
pub(crate) fn counts(reads: &Reads) -> (Counts<'_>, usize) {
    let mut support = Counts::new();
    let mut pairs = HashSet::<(&[u8], &[u8])>::new();
    for observed in reads.seqs.chunks_exact(4) {
        let first = identity(&observed[0], &observed[1]);
        let second = identity(&observed[2], &observed[3]);
        let key = if first <= second {
            (first, second)
        } else {
            (second, first)
        };
        if !pairs.insert(key) {
            continue;
        }
        for (index, (id, original)) in [(first, &observed[0]), (second, &observed[2])]
            .into_iter()
            .enumerate()
        {
            if index == 1 && first == second {
                continue;
            }
            let entry = support.entry(id).or_insert((original, 0));
            entry.1 += 1;
        }
    }
    (support, pairs.len())
}

pub(crate) fn has_kmers(id: &[u8]) -> bool {
    rolling_canonical_kmers(id).next().is_some()
}
