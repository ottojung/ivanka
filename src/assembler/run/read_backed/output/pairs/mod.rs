mod merge;
mod select;
#[cfg(test)]
mod test_negative;
#[cfg(test)]
mod tests;

use super::Entry;

pub(crate) fn observed(seqs: &[Vec<u8>], existing: &[Entry]) -> Vec<Entry> {
    select::choose(seqs, existing)
}
