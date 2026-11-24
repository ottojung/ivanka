pub(super) fn rc(seq: &[u8]) -> Vec<u8> {
    seq.iter()
        .rev()
        .map(|b| match b {
            b'A' => b'T',
            b'C' => b'G',
            b'G' => b'C',
            b'T' => b'A',
            _ => b'N',
        })
        .collect()
}

pub(super) fn add(data: &mut super::Reads, first: &[u8], base: u64, count: u64) {
    for n in 0..count {
        let mate = super::tests::sequence(60, base + n);
        data.seqs
            .extend([first.to_vec(), rc(first), mate.clone(), rc(&mate)]);
    }
}

pub(super) fn paired(fragment: &[u8], mate: &[u8], copies: usize) -> Vec<Vec<u8>> {
    let mut seqs = Vec::new();
    for _ in 0..copies {
        let f = fragment.to_vec();
        let rc_f = rc(fragment);
        let m = mate.to_vec();
        let rc_m = rc(mate);
        seqs.extend([f, rc_f, m, rc_m]);
    }
    seqs
}
