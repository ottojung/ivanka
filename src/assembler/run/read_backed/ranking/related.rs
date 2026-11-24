/// Original pairs whose discriminating 31-mers support one candidate alone.
///
/// A candidate's bit is set on a pair when at least two distinct loci of that
/// pair come from 31-mers no other candidate shares. Pairs carrying an
/// already-selected candidate's bit are ignored: a fragment explained by a
/// retained component cannot also establish a second, related component.
pub(super) fn counts(masks: &[u16], selected: u16, len: usize) -> Vec<usize> {
    let mut counts = vec![0; len];
    for &mask in masks {
        if mask == 0 || mask & selected != 0 {
            continue;
        }
        let mut bits = mask;
        while bits != 0 {
            counts[bits.trailing_zeros() as usize] += 1;
            bits &= bits - 1;
        }
    }
    counts
}
