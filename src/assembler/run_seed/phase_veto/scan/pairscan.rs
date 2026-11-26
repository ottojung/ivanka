use super::band;
use super::record;

pub(crate) fn unsupported_pair(
    seq: &[u8],
    calls: &[Vec<(usize, u8)>],
    sigs: &[u32],
    var: &[usize],
    max_span: usize,
) -> bool {
    let nv = var.len();
    if nv < 2 {
        return false;
    }
    let mut at = vec![usize::MAX; seq.len() + 1];
    for (i, &p) in var.iter().enumerate() {
        at[p] = i;
    }
    let off = band::build(var, max_span);
    let m = off[nv];
    if m == 0 {
        return false;
    }
    let mut ref_seen = vec![false; m];
    let mut ids = vec![[0u32; 8]; m];
    let mut counts = vec![0u8; m];
    {
        let mut rec = record::Recorder {
            seq,
            at: &at,
            var,
            off: &off,
            ref_seen: &mut ref_seen,
            ids: &mut ids,
            counts: &mut counts,
        };
        for (g, group) in calls.iter().enumerate() {
            rec.record(group, sigs[g]);
        }
    }
    for i in 0..nv {
        for k in off[i]..off[i + 1] {
            if !ref_seen[k] && counts[k] >= 8 {
                return true;
            }
        }
    }
    false
}
