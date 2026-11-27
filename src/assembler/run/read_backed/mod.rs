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

#[cfg(feature = "ouj-funnel-trace")]
pub(super) use super::funnel;
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
    let hits = index::build(contigs);
    let statistics = scoring::count(contigs, reads, &hits);
    let chosen = ranking::best(contigs, &statistics);
    #[cfg(feature = "ouj-funnel-trace")]
    funnel::emit(
        path,
        "readback_before",
        &contigs
            .iter()
            .enumerate()
            .map(|(i, seq)| (i, seq.as_slice(), statistics.pairs[i]))
            .collect::<Vec<_>>(),
    )?;
    #[cfg(feature = "ouj-funnel-trace")]
    funnel::emit(
        path,
        "component_before",
        &[(chosen, contigs[chosen].as_slice(), statistics.pairs[chosen])],
    )?;
    selection(contigs.len(), chosen, &statistics);
    let mut selected = output::component(contigs, reads, &statistics, chosen);
    for candidate in ranking::additional(contigs, &statistics, chosen) {
        #[cfg(feature = "ouj-funnel-trace")]
        funnel::emit(
            path,
            "readback_additional",
            &[(candidate, contigs[candidate].as_slice(), statistics.pairs[candidate])],
        )?;
        selection(contigs.len(), candidate, &statistics);
        selected.extend(output::component(contigs, reads, &statistics, candidate));
    }
    #[cfg(feature = "ouj-funnel-trace")]
    funnel::emit(
        path,
        "tiling_after",
        &selected
            .iter()
            .enumerate()
            .map(|(i, entry)| (i, entry.1.as_slice(), 0))
            .collect::<Vec<_>>(),
    )?;
    output::write(path, &selected)?;
    Ok(selected.len())
}
