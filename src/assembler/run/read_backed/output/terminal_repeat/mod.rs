//! Preserve read-derived paths without asserting ambiguous repeat phase.
use super::Entry;
mod tail;
#[cfg(test)]
mod test_prefix;
#[cfg(test)]
mod tests;

/// A terminal re-entry has the same evidential meaning on either strand.
/// Reverse temporarily, then reverse both original subpaths back into place.
pub(super) fn split(chosen: usize, seq: &[u8], read_len: usize) -> Option<Vec<Entry>> {
    let forward = tail::split(chosen, seq, read_len);
    let reversed = seq.iter().rev().copied().collect::<Vec<_>>();
    let reverse = tail::split(chosen, &reversed, read_len);
    match (forward, reverse) {
        (Some(_), Some(_)) => None,
        (Some(parts), None) => Some(parts),
        (None, Some(mut parts)) => {
            for (_, fragment) in &mut parts {
                fragment.reverse();
            }
            Some(parts)
        }
        (None, None) => None,
    }
}
