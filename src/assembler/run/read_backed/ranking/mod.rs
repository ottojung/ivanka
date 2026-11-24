mod independent;
mod junction;
mod spans;
use super::{scoring::Statistics, K};
pub(super) use independent::additional;
pub(super) use junction::junction;
use std::cmp::Ordering;

/// Render intervals in contig coordinates; without a detected unsupported
/// join this is the single whole contig and the established path is unchanged.
pub(super) fn pieces(joined: Option<(usize, usize)>, length: usize) -> Vec<(usize, usize)> {
    joined.map_or_else(
        || vec![(0, length)],
        |(a, b)| vec![(0, (a + K).min(length)), (b, length)],
    )
}

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
