use super::redundancy;
use super::{HashMap, HashSet};

// Read-support classification must never depend on alignment references.
pub(super) fn evaluate(
    seq: &[u8],
    support: usize,
    represented: &HashSet<u64>,
    retained: &[Vec<u8>],
    retained_support: &[usize],
    sampled: &HashMap<u64, u32>,
) -> (usize, usize, bool, bool) {
    let (valid, shared, short_shadow) = redundancy::overlap(seq, represented, retained);
    let snv =
        redundancy::is_supported_alternative(seq, support, retained, retained_support, sampled);
    (valid, shared, short_shadow, snv)
}
