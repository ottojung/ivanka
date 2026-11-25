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

use super::{encode, Reads, K};
use std::io;

type Entry = (String, Vec<u8>);

fn selection(native: usize, chosen: usize, stats: &scoring::Statistics) {
    eprintln!("IVANKA_READ_BACKED_SELECTION native {native} selected [{chosen}] covered_31mers [{}] supporting_pairs [{}] read_support_products [{}]", stats.coverage[chosen], stats.pairs[chosen], stats.coverage[chosen] * stats.pairs[chosen]);
}

pub(super) fn write(path: &str, contigs: &[Vec<u8>], reads: &Reads) -> io::Result<usize> {
    if contigs.is_empty() {
        return output::write(path, &[]).map(|()| 0);
    }
    debug_assert!(
        contigs.len() <= 16,
        "default pair masks hold at most sixteen candidates"
    );
    let hits = index::build(contigs);
    let statistics = scoring::count(contigs, reads, &hits);
    let chosen = ranking::best(contigs, &statistics);
    selection(contigs.len(), chosen, &statistics);
    let mut selected = output::component(contigs, reads, &statistics, chosen);
    let mut indices = vec![chosen];
    for candidate in ranking::additional(contigs, &statistics, chosen) {
        selection(contigs.len(), candidate, &statistics);
        selected.extend(output::component(contigs, reads, &statistics, candidate));
        indices.push(candidate);
    }
    if ranking::unlinked::flanks(contigs, &statistics, &indices) {
        selected = vec![unite(selected)];
    }
    output::write(path, &selected)?;
    Ok(selected.len())
}

/// Present disjoint read-backed flanks as one native, unbridged contig.
fn unite(entries: Vec<Entry>) -> Entry {
    let mut sequence = Vec::new();
    for (_, piece) in entries {
        sequence.extend(piece);
    }
    (format!(">ivanka_1 len={}", sequence.len()), sequence)
}
