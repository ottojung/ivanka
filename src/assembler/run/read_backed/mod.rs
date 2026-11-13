//! Original-pair evidence selects a defensible dominant contig without references.
mod cycles;
mod index;
mod island;
mod output;
mod ranking;
mod scoring;
#[cfg(test)]
mod tests;
mod tiling;
mod trimming;

use super::{Reads, K};
use std::io;

type Entry = (String, Vec<u8>);

pub(super) fn write(path: &str, contigs: &[Vec<u8>], reads: &Reads) -> io::Result<usize> {
    if contigs.is_empty() {
        return output::write(path, &[]).map(|()| 0);
    }
    let hits = index::build(contigs);
    let statistics = scoring::count(contigs, reads, &hits);
    let chosen = ranking::best(contigs, &statistics);
    let sequence = &contigs[chosen];
    let header = format!(">ivanka_{} len={}", chosen + 1, sequence.len());
    let depth = &statistics.depth[chosen];
    let (start, end) = island::bounds(sequence, depth);
    let clipped = &sequence[start..end];
    let observed = &depth[start..end.saturating_sub(K - 1).max(start)];
    let selected = cycles::alternatives(&header, clipped, reads)
        .unwrap_or_else(|| tiling::partition(&header, clipped, observed));
    eprintln!(
        "IVANKA_READ_BACKED_SELECTION native {} selected [{}] covered_31mers [{}] supporting_pairs [{}] read_support_products [{}]",
        contigs.len(), chosen, statistics.coverage[chosen], statistics.pairs[chosen],
        statistics.coverage[chosen] * statistics.pairs[chosen]
    );
    output::write(path, &selected)?;
    Ok(selected.len())
}
