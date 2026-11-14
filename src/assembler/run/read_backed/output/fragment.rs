use super::{circle, island, tiling, Entry, Reads, Statistics, K};

/// Preserve read-backed components independently: no unobserved joins.
pub(crate) fn component(
    contigs: &[Vec<u8>],
    stats: &Statistics,
    reads: &Reads,
    chosen: usize,
) -> Vec<Entry> {
    let repaired = circle::repair(&contigs[chosen], &stats.depth[chosen], reads);
    let (sequence, depth): (&[u8], &[u32]) = match &repaired {
        Some((seq, depths)) => (seq, depths),
        None => (&contigs[chosen], &stats.depth[chosen]),
    };
    if repaired.is_some() {
        eprintln!("IVANKA_READ_BACKED_REOPENED_CYCLE len={}", sequence.len());
    }
    let (start, end) = island::bounds(sequence, depth);
    let observed = &depth[start..end.saturating_sub(K - 1).max(start)];
    let header = format!(">ivanka_{} len={}", chosen + 1, sequence.len());
    let core = &sequence[start..end];
    if let Some(cut) = circle::unbridged_cut(core, reads) {
        eprintln!(
            "IVANKA_READ_BACKED_UNBRIDGED_JUNCTION cut={} len={}",
            cut,
            core.len()
        );
        let left = tiling::partition(
            &part_header(chosen, 1, cut),
            &core[..cut],
            &observed[..cut - K + 1],
        );
        let right = tiling::partition(
            &part_header(chosen, 2, core.len() - cut),
            &core[cut..],
            &observed[cut..],
        );
        return left.into_iter().chain(right).collect();
    }
    tiling::partition(&header, core, observed)
}

/// Unique FASTA IDs matter because MiCall keys BLAST genotypes by record.name.
pub(crate) fn part_header(chosen: usize, part: usize, len: usize) -> String {
    format!(">ivanka_{}_part{} len={}", chosen + 1, part, len)
}
