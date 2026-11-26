// Frozen pre-band reference algorithm, compiled only under cfg(test), used to
// prove that the banded scan returns the identical verdict. Never used in
// production; no reference, panel or score input.
pub(super) fn unsupported_pair(
    seq: &[u8],
    calls: &[Vec<(usize, u8)>],
    sigs: &[u32],
    var: &[usize],
    max_span: usize,
) -> bool {
    let nv = var.len();
    let mut at = vec![usize::MAX; seq.len() + 1];
    for (i, &p) in var.iter().enumerate() {
        at[p] = i;
    }
    let n = nv * nv;
    let mut ref_seen = vec![false; n];
    let mut ids = vec![[0u32; 8]; n];
    let mut counts = vec![0u8; n];
    for (g, group) in calls.iter().enumerate() {
        let got: Vec<(usize, u8)> = group
            .iter()
            .filter_map(|&(p, b)| (p < at.len() && at[p] != usize::MAX).then_some((at[p], b)))
            .collect();
        let sid = sigs[g];
        for x in 0..got.len() {
            for y in x + 1..got.len() {
                let (a, ba) = got[x];
                let (c, bc) = got[y];
                let (i, j) = (a.min(c), a.max(c));
                if var[j] - var[i] > max_span {
                    continue;
                }
                let k = i * nv + j;
                if ba == seq[var[i]] && bc == seq[var[j]] {
                    ref_seen[k] = true;
                    continue;
                }
                if ref_seen[k] {
                    continue;
                }
                let cnt = &mut counts[k];
                if *cnt < 8 && !ids[k][..*cnt as usize].contains(&sid) {
                    ids[k][*cnt as usize] = sid;
                    *cnt += 1;
                }
            }
        }
    }
    super::legacy_final::decide(&ref_seen, &counts, nv)
}
