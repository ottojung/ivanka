pub(super) fn best_long(
    more: Vec<Vec<u8>>,
    supports: Vec<usize>,
    original: &[Vec<u8>],
) -> Option<(Vec<u8>, usize)> {
    more.into_iter()
        .zip(supports)
        .filter(|(seq, support)| {
            seq.len() >= 1000
                && *support > 0
                && !original
                    .iter()
                    .any(|c| c.windows(seq.len()).any(|w| w == seq))
        })
        .max_by_key(|(seq, support)| (*support as u128) * (seq.len() as u128))
}
