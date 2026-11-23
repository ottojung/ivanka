//! Read-backed, reference-free assembly preserving distinct supported components.
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

use super::{encode, rolling_canonical_kmers, Reads, K};
use std::io;

type Entry = (String, Vec<u8>);

pub(super) fn write(path: &str, contigs: &[Vec<u8>], reads: &Reads) -> io::Result<usize> {
    if contigs.is_empty() {
        return output::write(path, &[]).map(|()| 0);
    }
    let hits = index::build(contigs);
    let stats = scoring::count(contigs, reads, &hits);
    let keep = ranking::supported_components(contigs, &stats);
    let mut output_contigs = Vec::new();
    for &candidate in &keep {
        let entries = output::one(contigs, &stats, reads, candidate);
        let room = 16usize.saturating_sub(output_contigs.len());
        output_contigs.extend(entries.into_iter().take(room));
        if output_contigs.len() == 16 {
            break;
        }
    }
    eprintln!(
        "IVANKA_READ_BACKED_SELECTION native {} selected {:?} covered_31mers {:?} supporting_pairs {:?}",
        contigs.len(), keep,
        keep.iter().map(|&i| stats.coverage[i]).collect::<Vec<_>>(),
        keep.iter().map(|&i| stats.pairs[i]).collect::<Vec<_>>()
    );
    output::write(path, &output_contigs)?;
    Ok(output_contigs.len())
}
