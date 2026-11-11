use super::{decode, extend, HashSet, Reads};

/// Independently examine the highest-depth seeds within the rescue budget.
/// Repeated seed identities are skipped; contigs are not consumed or merged.
pub(super) fn assemble_deep(
    reads: &Reads,
    contigs: &mut Vec<Vec<u8>>,
    supporting_counts: &mut Vec<usize>,
    rescue_limit: usize,
    attempted_seeds: &HashSet<u64>,
) {
    let mut deep = reads
        .seed_counts
        .iter()
        .filter(|(_, count)| **count >= 15)
        .map(|(&seed, &count)| (seed, count))
        .collect::<Vec<_>>();
    deep.sort_unstable_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
    let mut rescued = 0usize;
    for (seed, count) in deep.into_iter().take(rescue_limit) {
        // Re-running deterministic extension on an identical anchor adds no contig.
        if attempted_seeds.contains(&seed) {
            continue;
        }
        let (seq, support) = extend(decode(seed), &reads, 4, 1);
        if seq.is_empty() {
            continue;
        }
        if !contigs
            .iter()
            .any(|c| c.windows(seq.len()).any(|w| w == seq))
        {
            contigs.push(seq);
            supporting_counts.push(support);
            rescued += 1;
        }
        if rescued % 20 == 0 && rescued > 0 {
            eprintln!("high-depth rescue considered seed support {}", count);
        }
    }
    eprintln!(
        "Ivanka supplementary high-depth seeds produced {} novel contigs",
        rescued
    );
}
