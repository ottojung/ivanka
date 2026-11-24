mod accumulate;
mod scan;
mod spans;
mod statistics;
#[cfg(test)]
mod tests;
use super::{index, Reads, K};
#[cfg(test)]
use accumulate::Accumulator;
pub(super) use index::Hits;
pub(super) use statistics::Statistics;

/// Count each original read pair once per contig, irrespective of hit count.
/// The output is identical to the pairwise HashMap/HashSet formulation, with
/// per-pair original-fragment spans recorded for the coverage-hole junction
/// rule. No reference, truth or environment knob participates.
pub(super) fn count(contigs: &[Vec<u8>], reads: &Reads, hits: &Hits) -> Statistics {
    let (depth, pairs, pair_masks, spans) = scan::scan(contigs, reads, hits);
    let coverage = spans::coverage(&depth);
    Statistics {
        depth,
        pairs,
        coverage,
        pair_masks,
        spans,
    }
}
