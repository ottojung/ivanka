use super::{index::Hits, scoring::Statistics, Reads, K};
use std::cmp::Ordering;

/// Read-covered breadth squared, weighted by supporting original fragments.
fn compare(a: usize, b: usize, contigs: &[Vec<u8>], stats: &Statistics) -> Ordering {
    let (x, y) = (stats.coverage[a] as u128, stats.coverage[b] as u128);
    let (p, q) = (stats.pairs[a] as u128, stats.pairs[b] as u128);
    let (m, n) = (
        contigs[a].len().saturating_sub(30).max(1) as u128,
        contigs[b].len().saturating_sub(30).max(1) as u128,
    );
    let ratio = (y * y * q * m).cmp(&(x * x * p * n));
    ratio
        .then_with(|| (y * q).cmp(&(x * p)))
        .then_with(|| y.cmp(&x))
        .then_with(|| q.cmp(&p))
        .then_with(|| contigs[b].len().cmp(&contigs[a].len()))
        .then_with(|| a.cmp(&b))
}

pub(super) fn best(contigs: &[Vec<u8>], stats: &Statistics) -> usize {
    (0..contigs.len())
        .min_by(|&a, &b| compare(a, b, contigs, stats))
        .expect("caller requires at least one contig")
}

/// Prefer a coherent path only with comparable original-pair support.
pub(super) fn best_coherent(
    contigs: &[Vec<u8>],
    stats: &Statistics,
    ambiguous: impl Fn(usize) -> bool,
) -> usize {
    let first = best(contigs, stats);
    if !ambiguous(first) {
        return first;
    }
    (0..contigs.len())
        .filter(|&i| {
            !ambiguous(i)
                && (stats.pairs[i] as u128) * 10 >= (stats.pairs[first] as u128) * 9
                && (stats.coverage[i] as u128) * 5 >= (stats.coverage[first] as u128) * 3
        })
        .min_by(|&a, &b| compare(a, b, contigs, stats))
        .unwrap_or(first)
}

mod distinct;
#[cfg(test)]
pub(super) use distinct::complement;
pub(super) use distinct::complements;

mod molecules;
pub(super) use molecules::{links, PairLinks};
