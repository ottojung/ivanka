use super::{CYCLE_MATCH, CYCLE_MIN_SPACING};
pub(crate) fn repeats(
    seq: &[u8],
    j: usize,
    i: usize,
    k: usize,
    encode: fn(&[u8]) -> Option<u64>,
) -> bool {
    if i - j < CYCLE_MIN_SPACING || seq[j..j + CYCLE_MATCH] != seq[i..i + CYCLE_MATCH] {
        return false;
    }
    // Eight distinct sampled anchors suffice; avoid allocating a HashSet for
    // every candidate cycle, especially in repetitive high-depth paths.
    let mut distinct = [0u64; 8];
    let mut count = 0;
    for anchor in seq[j..j + CYCLE_MATCH]
        .windows(k)
        .step_by(32)
        .filter_map(encode)
    {
        if !distinct[..count].contains(&anchor) {
            distinct[count] = anchor;
            count += 1;
            if count == 8 {
                return true;
            }
        }
    }
    false
}
