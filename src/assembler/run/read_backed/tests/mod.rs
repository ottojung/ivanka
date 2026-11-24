use super::{index, island, output, ranking, scoring, tiling, trimming, Reads, K};
mod independent_cases;
mod junction_cases;
mod junction_output_cases;
mod junction_span_cases;
mod packed;
mod ranking_cases;
mod tiling_cases;
mod tiling_offset_cases;
mod trimming_cases;

/// Dense flanking pair evidence with no fragment spanning the middle valley.
pub(super) fn dense_spans() -> Vec<(usize, usize)> {
    [vec![(500, 650); 100], vec![(1840, 1970); 100]].concat()
}
