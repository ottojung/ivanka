use super::{related, Statistics, K};

// Independent original fragments, rather than the length of a competing
// genome, determine whether a second densely covered component is useful.
// A fragment already explained by a retained component cannot vote again.
// Closely related strains share most of their 31-mers, so their pairs also
// cannot vote through ordinary masks; discriminating 31-mers supply a second,
// read-derived qualification for a genuinely distinct haplotype.
pub(in super::super) fn additional(
    contigs: &[Vec<u8>],
    stats: &Statistics,
    primary: usize,
) -> Vec<usize> {
    if contigs.len() < 2 {
        return Vec::new();
    }
    let supported = stats.pair_masks.iter().filter(|&&mask| mask != 0).count();
    let minimum = supported.div_ceil(10).max(20);
    let discriminating = stats.exclusive_masks.iter().filter(|&&m| m != 0).count();
    let related_minimum = discriminating.div_ceil(10).max(20);
    let mut selected = 1u16 << primary;
    let mut additional = Vec::new();
    loop {
        let counts = independent_counts(&stats.pair_masks, selected, contigs.len());
        let related = related::counts(&stats.exclusive_masks, selected, contigs.len());
        let next = (0..contigs.len())
            .filter(|&i| {
                let positions = contigs[i].len().saturating_sub(K - 1);
                selected & (1 << i) == 0
                    && positions > 0
                    && stats.coverage[i] * 5 >= positions * 4
                    && ((counts[i] >= minimum && counts[i] * 5 >= stats.pairs[i] * 4)
                        || (related[i] >= related_minimum
                            && related[i] * 5 >= stats.pairs[i]
                            && related::uniform(&stats.depth[i])))
            })
            .max_by_key(|&i| (counts[i], stats.coverage[i], std::cmp::Reverse(i)));
        let Some(next) = next else { break };
        selected |= 1 << next;
        additional.push(next);
    }
    additional
}

fn independent_counts(masks: &[u16], selected: u16, count: usize) -> Vec<usize> {
    let mut counts = vec![0; count];
    for &mask in masks.iter().filter(|&&mask| mask & selected == 0) {
        let mut remaining = mask;
        while remaining != 0 {
            counts[remaining.trailing_zeros() as usize] += 1;
            remaining &= remaining - 1;
        }
    }
    counts
}
