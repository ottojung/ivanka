//! Original-pair evidence selects a defensible dominant contig without references.
mod circle;
mod index;
mod island;
mod output;
mod ranking;
mod scoring;
#[cfg(test)]
mod tests;
mod tiling;
mod trimming;

use super::{encode, extend, Reads, K};
use std::io;

type Entry = (String, Vec<u8>);

pub(super) fn write(path: &str, contigs: &[Vec<u8>], reads: &Reads) -> io::Result<usize> {
    if contigs.is_empty() {
        return output::write(path, &[]).map(|()| 0);
    }
    let hits = index::build(contigs);
    let statistics = scoring::count(contigs, reads, &hits);
    let chosen = ranking::best(contigs, &statistics);
    let repaired = circle::repair(&contigs[chosen], &statistics.depth[chosen], reads);
    let reextended = repaired
        .as_ref()
        .and_then(|(seq, _)| circle::try_extend(seq, reads));
    let (sequence, depth): (&[u8], &[u32]) = match reextended.as_ref().or(repaired.as_ref()) {
        Some((seq, depths)) => (seq, depths),
        None => (&contigs[chosen], &statistics.depth[chosen]),
    };
    let header = format!(">ivanka_{} len={}", chosen + 1, sequence.len());
    if repaired.is_some() {
        eprintln!("IVANKA_READ_BACKED_REOPENED_CYCLE len={}", sequence.len());
    }
    let (start, end) = island::bounds(sequence, depth);
    let clipped = &sequence[start..end];
    let observed = &depth[start..end.saturating_sub(K - 1).max(start)];
    let selected = tiling::partition(&header, clipped, observed);
    eprintln!(
        "IVANKA_READ_BACKED_SELECTION native {} selected [{}] covered_31mers [{}] supporting_pairs [{}] read_support_products [{}]",
        contigs.len(), chosen, statistics.coverage[chosen], statistics.pairs[chosen],
        statistics.coverage[chosen] * statistics.pairs[chosen]
    );
    output::write(path, &selected)?;
    Ok(selected.len())
}
