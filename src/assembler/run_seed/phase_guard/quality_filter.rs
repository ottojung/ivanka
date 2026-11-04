// Phred+33 Q15: both exact flanks and observed variant base must be high quality.
pub(super) fn low_quality_prefix(quality: &[u8]) -> Vec<usize> {
    let mut out=Vec::with_capacity(quality.len()+1);
    out.push(0);
    for &q in quality {
        out.push(out.last().copied().unwrap()+usize::from(q < 48));
    }
    out
}
pub(super) fn valid_window(prefix:&[usize],start:usize,end:usize)->bool {
    end<prefix.len() && start<=end && prefix[start]==prefix[end]
}
