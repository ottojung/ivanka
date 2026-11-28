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

pub(super) fn revcomp(seq: &[u8]) -> Vec<u8> {
    seq.iter()
        .rev()
        .map(|base| match base {
            b'A' => b'T',
            b'C' => b'G',
            b'G' => b'C',
            b'T' => b'A',
            _ => b'N',
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

/// A path, unique flank and second copy. Pair spans are short and varied near
/// the flanks; `spanning` adds a few genuinely crossing pairs with different
/// endpoints rather than many copies of one wide interval.
pub(super) fn fixture(second: Vec<u8>, spanning: bool) -> (Vec<u8>, Vec<u32>, Vec<(usize, usize)>) {
    let mut seq = path(0x1234_5678_9abc_def0, 4000);
    seq.extend(path(0xfeed_face_cafe_babe, 1000));
    seq.extend(second);
    let depth = vec![120u32; seq.len() - 30];
    let mut spans: Vec<(usize, usize)> = (0..30).map(|n| (0, 200 + 10 * n)).collect();
    spans.extend((0..30).map(|n| (5600 - 5 * n, 5800 - 5 * n)));
    if spanning {
        for boundary in (2000..=7000).step_by(1000) {
            spans.extend((0..12).map(|n| (boundary - 50 + n, boundary + 250 + n)));
        }
    }
    (seq, depth, spans)
}
