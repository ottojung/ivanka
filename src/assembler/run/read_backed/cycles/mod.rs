//! Preserve both read-derived linear explanations of an ambiguous cycle.
pub(super) mod detect;
mod spans;
pub(super) mod variants;
use super::{Entry, Reads};

pub(super) fn alternatives(header: &str, sequence: &[u8], reads: &Reads) -> Option<Vec<Entry>> {
    if sequence.len() < 2_000 {
        return None;
    }
    let overlap = detect::terminal_overlap(sequence);
    if overlap < 200 || overlap > sequence.len() / 3 {
        return None;
    }
    let depths = spans::count(sequence, reads);
    let (start, end) = detect::unsupported_gap(&depths)?;
    let candidates = variants::build(header, sequence, overlap, start, end);
    eprintln!(
        "IVANKA_UNPHASED_JOIN {}-{} repeated={} variants={}",
        start, end, overlap, candidates.len()
    );
    Some(candidates)
}
