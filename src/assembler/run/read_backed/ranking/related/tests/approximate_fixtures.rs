//! Truth-free fixtures for the conservative approximate-repeat junction.

pub(super) fn path(seed: u64, length: usize) -> Vec<u8> {
    let mut state = seed;
    (0..length)
        .map(|_| {
            state = state.wrapping_mul(6364136223846793005).wrapping_add(1);
            [b'A', b'C', b'G', b'T'][((state >> 33) & 3) as usize]
        })
        .collect()
}

pub(super) fn diverged(source: &[u8]) -> Vec<u8> {
    let mut copy = source.to_vec();
    for position in (0..copy.len()).step_by(20) {
        copy[position] = match copy[position] {
            b'A' => b'C',
            b'C' => b'G',
            b'G' => b'T',
            _ => b'A',
        };
    }
    copy
}

/// A path, unique flank and second copy, with original pairs on either side
/// of the transition and, when `supported`, additional pairs across it.
pub(super) fn fixture(
    second: Vec<u8>,
    supported: bool,
) -> (Vec<u8>, Vec<u32>, Vec<(usize, usize)>) {
    let mut seq = path(0x1234_5678_9abc_def0, 4000);
    seq.extend(path(0xfeed_face_cafe_babe, 1000));
    seq.extend(second);
    let depth = vec![120u32; seq.len() - 30];
    let mut spans = vec![(0, 1400); 40];
    spans.extend(vec![(5600, 8800); 40]);
    if supported {
        spans.extend(vec![(1900, 5100); 40]);
    }
    (seq, depth, spans)
}
