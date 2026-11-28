use super::Reads;
use std::collections::{HashMap, HashSet};

pub(crate) fn identity<'a>(forward: &'a [u8], reverse: &'a [u8]) -> &'a [u8] {
    if forward <= reverse {
        forward
    } else {
        reverse
    }
}

/// One observed (read, mate) pair for each canonical read identity.
///
/// Only the first distinct observed pair is kept, so a jackpot of identical
/// pairs cannot supply many mates or hidden copies. All identities are
/// borrowed slices from the loaded reads.
pub(crate) fn pairs(reads: &Reads) -> HashMap<&[u8], (&[u8], &[u8])> {
    let mut seen = HashSet::<(&[u8], &[u8])>::new();
    let mut found = HashMap::new();
    for observed in reads.seqs.chunks_exact(4) {
        let first = identity(&observed[0], &observed[1]);
        let second = identity(&observed[2], &observed[3]);
        let key = if first <= second {
            (first, second)
        } else {
            (second, first)
        };
        if !seen.insert(key) {
            continue;
        }
        found
            .entry(first)
            .or_insert((observed[0].as_slice(), observed[2].as_slice()));
        if first != second {
            found
                .entry(second)
                .or_insert((observed[2].as_slice(), observed[0].as_slice()));
        }
    }
    found
}
