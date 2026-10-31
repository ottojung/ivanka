use super::rc;

// Restore read-supported phased alternatives only into otherwise unused slots.
// Never evict a baseline-selected contig; exact whole-path containment in
// either orientation is the only reason to omit a deferred alternative.
pub(super) fn append_phased(retained:&mut Vec<Vec<u8>>, deferred:Vec<Vec<u8>>, cap:usize)->usize {
    let before=retained.len();
    for seq in deferred {
        if retained.len()>=cap {break;}
        let reverse=rc(&seq);
        if retained.iter().any(|c|c.windows(seq.len())
            .any(|w|w==seq || w==reverse)) {continue;}
        retained.push(seq);
    }
    retained.len()-before
}
