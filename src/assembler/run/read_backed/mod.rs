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

pub(super) fn write(path: &str, contigs: &[Vec<u8>], reads: &Reads) -> io::Result<usize> {
    if contigs.is_empty() {
        return output::write(path, &[]).map(|()| 0);
    }
    let hits = index::build(contigs);
    let statistics = scoring::count(contigs, reads, &hits);
    let chosen = ranking::best(contigs, &statistics);
    let mut selected = output::component(contigs, &statistics, reads, chosen);
    let linked = ranking::links(reads, &hits);
    for other in ranking::complements(contigs, &statistics, &hits, chosen, &linked) {
        let extra = output::component(contigs, &statistics, reads, other);
        if selected.len() + extra.len() <= 16 {
            eprintln!(
                "IVANKA_READ_BACKED_DISTINCT_COMPONENT secondary={} original_pairs={}",
                other, statistics.pairs[other]
            );
            selected.extend(extra);
        }
    }
    let original_pairs = output::observed(&reads.seqs, &selected);
    if !original_pairs.is_empty() {
        eprintln!(
            "IVANKA_ORIGINAL_PAIR_FRAGMENTS retained={}",
            original_pairs.len()
        );
        selected.extend(original_pairs);
    }
    eprintln!(
        "IVANKA_READ_BACKED_SELECTION native {} selected [{}] covered_31mers [{}] supporting_pairs [{}] read_support_products [{}]",
        contigs.len(), chosen, statistics.coverage[chosen], statistics.pairs[chosen],
        statistics.coverage[chosen] * statistics.pairs[chosen]
    );
    output::write(path, &selected)?;
    Ok(selected.len())
}
