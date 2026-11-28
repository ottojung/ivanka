use super::{balanced, private, related, retained, Statistics, K};

// Independent original fragments, rather than the length of a competing
// genome, determine whether a second densely covered component is useful.
// Homologous strains share most fragments, so a read-supported private
// stretch can establish a distinct branch where no fragment votes alone.
// When even the private stretches are shared, discriminating original-pair
// 31-mers supply a second, reference-blind qualification for a genuinely
// distinct, co-abundant haplotype.
pub(in super::super) fn additional(
    contigs: &[Vec<u8>],
    stats: &Statistics,
    primary: usize,
) -> Vec<usize> {
    if contigs.len() < 2 {
        return Vec::new();
    }
    let minimum = related::minimum(&stats.pair_masks);
    let related_minimum = related::minimum(&stats.exclusive_masks);
    let mut selected = 1u16 << primary;
    let mut additional = Vec::new();
    loop {
        let counts = related::counts(&stats.pair_masks, selected, contigs.len());
        let related = related::counts(&stats.exclusive_masks, selected, contigs.len());
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
                let pairs = stats.pairs[i];
                let strong = counts[i] >= minimum && counts[i] * 5 >= pairs * 4
                    || balanced::qualifies(contigs, stats, selected, primary, i)
                    || related::qualifies(related[i], related_minimum, pairs, stats, selected, i);
                private::qualifies(evidence[i], positions, strong)
            })
            .max_by_key(|&i| {
                (
                    counts[i],
                    evidence[i].0,
                    stats.coverage[i],
                    std::cmp::Reverse(i),
                )
            });
        let Some(next) = next else { break };
        selected |= 1 << next;
        additional.push(next);
    }
    additional
}
