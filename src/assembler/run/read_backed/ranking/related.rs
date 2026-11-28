#[cfg(test)]
pub(super) use super::additional;
pub(super) use super::{approximate_junction, junction, spans::seed as short_seed, Statistics, K};
pub(super) use render::pieces_keep_middle;
mod diversity;
pub(super) mod render;
#[cfg(test)]
mod tests;

/// One tenth of the voted pairs, with an absolute floor. Used for both the
/// ordinary mask count and the exclusive-mask count: the latter counts every
/// pair carrying discriminating evidence, so a second phase needs a real
/// share of it even when the dominant candidate consumes its own pairs.
pub(super) fn minimum(masks: &[u16]) -> usize {
    masks
        .iter()
        .filter(|&&m| m != 0)
        .count()
        .div_ceil(10)
        .max(20)
}

/// Count one vote per candidate bit on every pair not already explained by a
/// selected component. Used for ordinary pair masks and, with exclusive masks,
/// for original pairs whose discriminating 31-mers support one candidate
/// alone: a fragment explained by a retained component cannot vote again for
/// a second, related component.
pub(super) fn counts(masks: &[u16], selected: u16, len: usize) -> Vec<usize> {
    let mut counts = vec![0; len];
    for &mask in masks {
        if mask == 0 || mask & selected != 0 {
            continue;
        }
        let mut bits = mask;
        while bits != 0 {
            counts[bits.trailing_zeros() as usize] += 1;
            bits &= bits - 1;
        }
    }
    counts
}

/// A related component must be one uninterrupted read-supported island.
/// Fragmented depth would be rendered as several tiles, which cannot support
/// a single haplotype claim. Mirrors the tiling presentation rule.
pub(super) fn uniform(depth: &[u32]) -> bool {
    !depth.is_empty()
        && depth.iter().filter(|&&v| v >= 3).count() * 100 >= depth.len() * 95
        && depth.split(|&v| v >= 3).all(|gap| gap.len() < 100)
}

/// Conservative, reference-blind admission for a related component.
///
/// `minimum` is one tenth of all discriminating pairs (with an absolute
/// floor). The raw pair count is preserved; distinct read-pair signatures
/// and non-overlapping exclusive locus clusters are a lower-bound diversity
/// guard. A single-locus genuine strain is not impossible when many distinct
/// fragments support it, but ambiguous single-signature or overlapping-window
/// evidence is withheld conservatively. Truth never reaches this rule.
pub(super) fn qualifies(
    related: usize,
    minimum: usize,
    pairs: usize,
    stats: &super::Statistics,
    selected: u16,
    i: usize,
) -> bool {
    let (signatures, clusters) = diversity::diversity(stats, selected, i);
    related >= minimum
        && related * 5 >= pairs
        && uniform(stats.depth.get(i).map_or(&[], Vec::as_slice))
        && signatures >= 2
        && (clusters >= 2 || signatures >= minimum)
}
