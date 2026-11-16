use super::{distinct::not_independent, Entry, PairLinks, Statistics};

/// Decide only after read-backed output processing: splits are independent.
pub(crate) fn should_add(
    primary: usize,
    other: usize,
    contigs: &[Vec<u8>],
    stats: &Statistics,
    links: &PairLinks,
    selected: &[Entry],
    extra: &[Entry],
) -> bool {
    if selected.len() + extra.len() > 16 {
        return false;
    }
    let same_footprint = if selected.len() == 1 && extra.len() == 1 {
        let a = selected[0].1.len() as u128;
        let b = extra[0].1.len() as u128;
        a.min(b) * 10 >= a.max(b) * 9
    } else {
        false
    };
    if same_footprint && not_independent(other, primary, contigs, links, stats) {
        return false;
    }
    eprintln!(
        "IVANKA_READ_BACKED_DISTINCT_COMPONENT secondary={} original_pairs={}",
        other, stats.pairs[other]
    );
    true
}
