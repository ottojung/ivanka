use std::collections::{HashMap, HashSet};
/// A local SNV is reported only with multiple novel sampled 31-mer
/// witnesses. The observation is explicitly unphased: it is never used
/// to assert that an alternate base belongs to an assembled molecule.
pub(super) fn evidence(
    seq: &[u8],
    parent: &[u8],
    represented: &HashSet<u64>,
    sampled: &HashMap<u64, u32>,
    canonical: fn(&[u8]) -> Option<u64>,
) -> Option<(usize, usize, String)> {
    if parent.len() != seq.len() {
        return None;
    }
    let diffs = seq
        .iter()
        .zip(parent)
        .enumerate()
        .filter(|(_, (a, b))| a != b)
        .map(|(i, _)| i)
        .take(2)
        .collect::<Vec<_>>();
    if diffs.len() != 1 {
        return None;
    }
    let pos = diffs[0];
    if pos < 31 || pos + 31 >= seq.len() {
        return None;
    }
    let novel = seq[pos - 30..pos + 31]
        .windows(31)
        .filter_map(canonical)
        .filter(|k| !represented.contains(k) && sampled.get(k).copied().unwrap_or(0) >= 5)
        .collect::<HashSet<_>>();
    if novel.len() < 3 {
        return None;
    }
    let context = String::from_utf8_lossy(&seq[pos - 30..pos + 31]).into_owned();
    Some((pos, novel.len(), context))
}
