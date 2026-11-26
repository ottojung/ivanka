use super::band;

// One read-pair group records both direct candidate-allele support and up to
// eight distinct original-pair signatures per usable variant pair. Inputs are
// read-derived only; no reference, panel or score is consulted.
pub(super) struct Recorder<'a> {
    pub(super) seq: &'a [u8],
    pub(super) at: &'a [usize],
    pub(super) var: &'a [usize],
    pub(super) off: &'a [usize],
    pub(super) ref_seen: &'a mut [bool],
    pub(super) ids: &'a mut [[u32; 8]],
    pub(super) counts: &'a mut [u8],
}

impl Recorder<'_> {
    pub(super) fn record(&mut self, group: &[(usize, u8)], sid: u32) {
        let got: Vec<(usize, u8)> = group
            .iter()
            .filter_map(|&(p, b)| {
                (p < self.at.len() && self.at[p] != usize::MAX).then_some((self.at[p], b))
            })
            .collect();
        for x in 0..got.len() {
            for y in x + 1..got.len() {
                let (a, ba) = got[x];
                let (c, bc) = got[y];
                let (i, j) = (a.min(c), a.max(c));
                let Some(k) = band::slot(self.off, i, j) else {
                    continue;
                };
                if ba == self.seq[self.var[i]] && bc == self.seq[self.var[j]] {
                    self.ref_seen[k] = true;
                    continue;
                }
                if self.ref_seen[k] {
                    continue;
                }
                let cnt = &mut self.counts[k];
                if *cnt < 8 && !self.ids[k][..*cnt as usize].contains(&sid) {
                    self.ids[k][*cnt as usize] = sid;
                    *cnt += 1;
                }
            }
        }
    }
}
