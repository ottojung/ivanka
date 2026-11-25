/// Rotate a native contig at an unsupported internal join.
///
/// The two read-backed flanks keep their original orientation and every
/// emitted base is a native subsequence; nothing is invented across the gap.
pub(in super::super) fn native(
    sequence: &[u8],
    depth: &[u32],
    ab: (usize, usize),
) -> (Vec<u8>, Vec<u32>) {
    let (a, b) = ab;
    let head = (a + super::K).min(sequence.len());
    let mut seq = sequence[b..].to_vec();
    seq.extend_from_slice(&sequence[..head]);
    let mut dep = depth[b.min(depth.len())..].to_vec();
    dep.extend(std::iter::repeat(0).take(super::K - 1));
    let tail = (a + 1).min(depth.len());
    dep.extend_from_slice(&depth[..tail]);
    (seq, dep)
}
