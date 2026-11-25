use super::{private, retained, Statistics, K};

// Independent original fragments, rather than the length of a competing
// genome, determine whether a second densely covered component is useful.
// Homologous strains share most fragments, so a read-supported private
// stretch can establish a distinct branch where no fragment votes alone.
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
    let mut selected = 1u16 << primary;
    let mut additional = Vec::new();
    loop {
        let counts = independent_counts(&stats.pair_masks, selected, contigs.len());
        let chosen = (0..contigs.len())
            .filter(|&i| selected & (1 << i) != 0)
            .collect::<Vec<_>>();
        let evidence = private::scores(contigs, &stats.depth, &retained::keys(contigs, &chosen));
        let next = (0..contigs.len())
            .filter(|&i| {
                let positions = contigs[i].len().saturating_sub(K - 1);
                let covered = positions > 0 && stats.coverage[i] * 5 >= positions * 4;
                if selected & (1 << i) != 0 || !covered || stats.pairs[i] < minimum {
                    return false;
                }
                let strong = counts[i] >= minimum && counts[i] * 5 >= stats.pairs[i] * 4;
                private::qualifies(evidence[i], positions, strong)
            })
            .max_by_key(|&i| {
                let (private, _, _) = evidence[i];
                (counts[i], private, stats.coverage[i], std::cmp::Reverse(i))
            });
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
