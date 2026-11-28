// A mate is only merged when an exact overlap proves the two observations are
// adjacent on one original fragment. This is below the canonical 31-mer size
// because paired-end inserts leave a short exact suffix/prefix overlap, but
// long enough that an accidental match between unrelated reads is negligible.
const MIN_OVERLAP: usize = 16;

fn suffix_prefix(left: &[u8], right: &[u8]) -> Option<usize> {
    let longest = left.len().min(right.len());
    (MIN_OVERLAP..=longest)
        .rev()
        .find(|&n| left[left.len() - n..] == right[..n])
}

/// Reconstruct one observed fragment from a read and its own mate.
///
/// Only exact observed bases are used: the longest exact suffix/prefix overlap
/// is trimmed, never filled or invented. If the mates do not overlap exactly,
/// or the mate is absent, the original read is returned unchanged. Both strand
/// orientations of the mate are considered; the pair identity itself is the
/// canonical (lexically smaller) read observed by `pair_support`.
pub(crate) fn merge(read: &[u8], mate: Option<&[u8]>) -> Vec<u8> {
    let Some(mate) = mate else {
        return read.to_vec();
    };
    let reversed = mate
        .iter()
        .rev()
        .map(|&b| match b {
            b'A' => b'T',
            b'C' => b'G',
            b'G' => b'C',
            b'T' => b'A',
            other => other,
        })
        .collect::<Vec<_>>();
    let mut best: Option<(usize, Vec<u8>)> = None;
    for (left, right) in [
        (read, mate),
        (read, reversed.as_slice()),
        (mate, read),
        (reversed.as_slice(), read),
    ] {
        let Some(n) = suffix_prefix(left, right) else {
            continue;
        };
        if best.as_ref().is_none_or(|&(length, _)| n > length) {
            let mut joined = left.to_vec();
            joined.extend_from_slice(&right[n..]);
            best = Some((n, joined));
        }
    }
    best.map(|(_, joined)| joined)
        .unwrap_or_else(|| read.to_vec())
}
