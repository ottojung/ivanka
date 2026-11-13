/// A closed path repeats an exact suffix at its beginning.
pub(super) fn length(sequence: &[u8], min: usize, max: usize) -> Option<usize> {
    (min..=max.min(sequence.len() / 2))
        .rev()
        .find(|&n| sequence[..n] == sequence[sequence.len() - n..])
}
