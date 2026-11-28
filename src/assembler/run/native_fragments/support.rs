use super::pair_support;
use super::Reads;

/// Minimum number of distinct observed pairs supporting a retained fragment.
pub(super) const MIN_SUPPORT: usize = 15;

/// Minimum share of the library's distinct observed pairs for a fragment.
/// Trace components (for example contamination) must not consume contig slots.
pub(super) const MIN_SHARE_NUMERATOR: usize = 1;
pub(super) const MIN_SHARE_DENOMINATOR: usize = 100;

/// Rank observed reads by their distinct observed-pair support.
///
/// Pair identity is the unordered pair of canonical mate identities, so a
/// mate and its reverse complement are one observation. Both mates of one
/// pair contribute at most one vote per identity. All slices are borrowed
/// from the loaded reads; only surviving candidates are copied by the caller.
pub(super) fn ranked(reads: &Reads) -> Vec<(&[u8], usize)> {
    let (support, total) = pair_support::counts(reads);
    let mut candidates = support
        .into_iter()
        .filter(|&(id, (_, n))| {
            n >= MIN_SUPPORT
                && n.saturating_mul(MIN_SHARE_DENOMINATOR)
                    >= total.saturating_mul(MIN_SHARE_NUMERATOR)
                && pair_support::has_kmers(id)
        })
        .map(|(_, (original, n))| (original, n))
        .collect::<Vec<_>>();
    candidates.sort_by(|a, b| {
        b.1.cmp(&a.1)
            .then_with(|| b.0.len().cmp(&a.0.len()))
            .then_with(|| a.0.cmp(b.0))
    });
    candidates
}
