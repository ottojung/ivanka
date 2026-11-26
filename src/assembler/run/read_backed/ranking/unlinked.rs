//! Read-backed admission for disjoint flanks of one unsupported locus.
use super::{Statistics, K};

/// Two broadly covered components that almost never occur in the same
/// original fragment are flanks of a locus with no spanning read evidence,
/// not alternative haplotypes. No truth, reference or case identity is used.
pub(in super::super) fn flanks(contigs: &[Vec<u8>], stats: &Statistics, indices: &[usize]) -> bool {
    if indices.len() < 2 {
        return false;
    }
    let mask = indices.iter().fold(0u16, |m, &i| m | (1 << i));
    let linked = stats
        .pair_masks
        .iter()
        .filter(|&&m| m & mask == mask)
        .count();
    let supported = stats.pair_masks.iter().filter(|&&m| m & mask != 0).count();
    if supported == 0 || linked * 20 > supported {
        return false;
    }
    indices.iter().all(|&i| {
        let positions = contigs[i].len().saturating_sub(K - 1);
        positions >= 2000 && stats.coverage[i] * 5 >= positions * 4
    })
}
