use super::{rank, Reads};

/// Minimum number of distinct observed pairs supporting a retained fragment.
pub(super) const MIN_SUPPORT: usize = 15;

/// Minimum share of the library's distinct observed pairs for a fragment.
/// Trace components (for example contamination) must not consume contig slots.
pub(super) const MIN_SHARE_NUMERATOR: usize = 1;
pub(super) const MIN_SHARE_DENOMINATOR: usize = 100;

/// Rank observed fragments by their distinct observed-pair support.
///
/// Pair identity is the unordered pair of canonical mate identities, so a
/// mate and its reverse complement are one observation. Both mates of one
/// pair contribute at most one vote per identity. Where a read and its own
/// mate overlap exactly, the two observations are reconstructed into one
/// fragment: a high-copy disconnected region then consumes one contig slot
/// instead of two. All identities are borrowed slices from the loaded reads;
/// only surviving candidates are copied by the caller.
pub(super) fn ranked(reads: &Reads) -> Vec<(Vec<u8>, usize)> {
    let (support, total) = rank::counts(reads);
    let mates = rank::pairs(reads);
    let mut candidates = support
        .into_iter()
        .filter(|&(id, (_, n))| {
            n >= MIN_SUPPORT
                && n.saturating_mul(MIN_SHARE_DENOMINATOR)
                    >= total.saturating_mul(MIN_SHARE_NUMERATOR)
                && rank::has_kmers(id)
        })
        .flat_map(|(id, (original, n))| {
            let mate = mates.get(id).map(|&(_, mate)| mate);
            let merged = rank::merge(original, mate);
            if merged.as_slice() == original {
                vec![(merged, n)]
            } else {
                // Keep the single observation as a fallback: a longer merged
                // fragment can be vetoed by one represented 31-mer while its
                // still-disjoint read can occupy the same slot honestly.
                vec![(merged, n), (original.to_vec(), n)]
            }
        })
        .collect::<Vec<_>>();
    candidates.sort_by(|a, b| {
        b.1.cmp(&a.1)
            .then_with(|| b.0.len().cmp(&a.0.len()))
            .then_with(|| a.0.cmp(&b.0))
    });
    candidates
}
