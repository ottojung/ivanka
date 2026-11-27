#[cfg(test)]
pub(super) use super::additional;
#[cfg(test)]
pub(super) use super::Statistics;
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
/// floor), so the extra component must be supported by a substantial share
/// of the private evidence. Requiring at least one fifth of the candidate's
/// own original pairs prevents a tiny private island from carrying a phase,
/// and `uniform` excludes a tiled, gap-ridden candidate. Every input derives
/// from read pairs and candidate 31-mers only; truth never reaches this rule.
pub(super) fn qualifies(related: usize, minimum: usize, pairs: usize, depth: &[u32]) -> bool {
    related >= minimum && related * 5 >= pairs && uniform(depth)
}
