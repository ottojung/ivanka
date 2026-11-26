// Final dense-matrix decision for the frozen pre-band reference.
pub(super) fn decide(ref_seen: &[bool], counts: &[u8], nv: usize) -> bool {
    for i in 0..nv {
        for j in i + 1..nv {
            let k = i * nv + j;
            if !ref_seen[k] && counts[k] >= 8 {
                return true;
            }
        }
    }
    false
}
