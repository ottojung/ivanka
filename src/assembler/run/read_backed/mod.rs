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
    funnel::emit_all(path, "readback_before", contigs, &statistics.pairs)?;
    #[cfg(feature = "ouj-funnel-trace")]
    funnel::emit_one(path, "component_before", contigs, &statistics.pairs, chosen)?;
    selection(contigs.len(), chosen, &statistics);
    let mut selected = output::component(contigs, reads, &statistics, chosen);
    for candidate in ranking::additional(contigs, &statistics, chosen) {
        #[cfg(feature = "ouj-funnel-trace")]
        funnel::emit_one(
            path,
            "readback_additional",
            contigs,
            &statistics.pairs,
            candidate,
        )?;
        selection(contigs.len(), candidate, &statistics);
        selected.extend(output::component(contigs, reads, &statistics, candidate));
    }
    #[cfg(feature = "ouj-funnel-trace")]
    funnel::emit_selected(path, "tiling_after", &selected)?;
    output::write(path, &selected)?;
    Ok(selected.len())
}
