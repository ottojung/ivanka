use std::collections::HashMap;

/// A contiguous insert exists only when an original pair's ends overlap.
pub(super) fn insert(left: &[u8], right: &[u8]) -> Option<Vec<u8>> {
    if left.len() < 25 || right.len() < 25 {
        return None;
    }
    let overlap = (25..=left.len().min(right.len()))
        .rev()
        .find(|&len| left[left.len() - len..] == right[..len])?;
    let mut joined = left.to_vec();
    joined.extend_from_slice(&right[overlap..]);
    Some(joined)
}

pub(super) fn count(seqs: &[Vec<u8>]) -> (HashMap<Vec<u8>, usize>, usize) {
    let mut tally = HashMap::new();
    let mut pairs = 0;
    for original in seqs.chunks_exact(4).take(80_000) {
        pairs += 1;
        if let Some(joined) = insert(&original[0], &original[3]) {
            let reverse = crate::assembler::reads::rc(&joined);
            let canonical = if joined <= reverse { joined } else { reverse };
            *tally.entry(canonical).or_insert(0) += 1;
        }
    }
    (tally, pairs)
}
