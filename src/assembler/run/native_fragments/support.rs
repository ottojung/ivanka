use super::Reads;
use std::collections::{HashMap, HashSet};

/// Minimum number of distinct observed pairs supporting a retained fragment.
pub(super) const MIN_SUPPORT: usize = 15;

/// Minimum share of the library's distinct observed pairs for a fragment.
/// Trace components (for example contamination) must not consume contig slots.
pub(super) const MIN_SHARE_NUMERATOR: usize = 1;
pub(super) const MIN_SHARE_DENOMINATOR: usize = 100;

/// Rank reads by the number of distinct observed pairs they appear in.
/// Identical pair sequences are counted once; no molecule identity is assumed.
pub(super) fn ranked(reads: &Reads) -> Vec<(Vec<u8>, usize)> {
    let mut support = HashMap::<Vec<u8>, usize>::new();
    let mut pairs = HashSet::<(Vec<u8>, Vec<u8>)>::new();
    for observed in reads.seqs.chunks_exact(4).take(80_000) {
        if !pairs.insert((observed[0].clone(), observed[2].clone())) {
            continue;
        }
        *support.entry(observed[0].clone()).or_insert(0) += 1;
        *support.entry(observed[2].clone()).or_insert(0) += 1;
    }
    let total = pairs.len();
    let mut candidates = support
        .into_iter()
        .filter(|&(_, n)| {
            n >= MIN_SUPPORT
                && n.saturating_mul(MIN_SHARE_DENOMINATOR)
                    >= total.saturating_mul(MIN_SHARE_NUMERATOR)
        })
        .collect::<Vec<_>>();
    candidates.sort_by(|a, b| {
        b.1.cmp(&a.1)
            .then_with(|| b.0.len().cmp(&a.0.len()))
            .then_with(|| a.0.cmp(&b.0))
    });
    candidates
}
