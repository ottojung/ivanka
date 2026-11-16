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
    let chosen = ranking::best_coherent(contigs, &statistics, |i| {
        circle::ambiguous_tail(&contigs[i], &statistics.depth[i], K)
    });
    let mut selected = output::component(contigs, &statistics, reads, chosen);
    let linked = ranking::links(reads, &hits);
    for other in ranking::complements(contigs, &statistics, &hits, chosen, &linked) {
        let extra = output::component(contigs, &statistics, reads, other);
        if ranking::should_add(
            chosen,
            other,
            contigs,
            &statistics,
            &linked,
            &selected,
            &extra,
        ) {
            selected.extend(extra);
        }
    }
    output::append_observed(reads, &mut selected);
    eprintln!(
        "IVANKA_READ_BACKED_SELECTION native {} selected [{}] covered_31mers [{}] supporting_pairs [{}] read_support_products [{}]",
        contigs.len(), chosen, statistics.coverage[chosen], statistics.pairs[chosen],
        statistics.coverage[chosen] * statistics.pairs[chosen]
    );
    output::write(path, &selected)?;
    Ok(selected.len())
}
