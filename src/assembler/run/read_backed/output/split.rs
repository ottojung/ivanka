use super::{fragment::part_header, tiling, Entry, K};

/// Independent read-backed paths are never concatenated into a claimed haplotype.
pub(super) fn at(chosen: usize, sequence: &[u8], depth: &[u32], cut: usize) -> Vec<Entry> {
    let left = tiling::partition(
        &part_header(chosen, 1, cut),
        &sequence[..cut],
        &depth[..cut - K + 1],
    );
    let right = tiling::partition(
        &part_header(chosen, 2, sequence.len() - cut),
        &sequence[cut..],
        &depth[cut..],
    );
    left.into_iter().chain(right).collect()
}
