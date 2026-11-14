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
    let mut retained = vec![chosen];
    loop {
        let Some(other) = ranking::distinct(contigs, &statistics, &hits, &retained) else {
            break;
        };
        let extra = output::component(contigs, &statistics, reads, other);
        if selected.len() + extra.len() > 16 {
            eprintln!(
                "IVANKA_READ_BACKED_DISTINCT_COMPONENT withheld={} tile_budget",
                other
            );
            break;
        }
        eprintln!(
            "IVANKA_READ_BACKED_DISTINCT_COMPONENT secondary={} original_pairs={}",
            other, statistics.pairs[other]
        );
        selected.extend(extra);
        retained.push(other);
    }
    eprintln!(
        "IVANKA_READ_BACKED_SELECTION native {} selected [{}] covered_31mers [{}] supporting_pairs [{}] read_support_products [{}]",
        contigs.len(), chosen, statistics.coverage[chosen], statistics.pairs[chosen],
        statistics.coverage[chosen] * statistics.pairs[chosen]
    );
    output::write(path, &selected)?;
    Ok(selected.len())
}
