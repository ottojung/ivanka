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

pub(super) fn add(data: &mut super::super::Reads, first: &[u8], base: u64, count: u64) {
    for n in 0..count {
        let mate = super::sequence(60, base + n);
        data.seqs
            .extend([first.to_vec(), rc(first), mate.clone(), rc(&mate)]);
    }
}

pub(super) fn paired(fragment: &[u8], mate: &[u8], copies: usize) -> Vec<Vec<u8>> {
    let (f, m) = (fragment.to_vec(), mate.to_vec());
    let (rf, rm) = (rc(&f), rc(&m));
    (0..copies)
        .flat_map(|_| [f.clone(), rf.clone(), m.clone(), rm.clone()])
        .collect()
}

// Two 150-base mates of one 270-base observed fragment, overlapping by 30.
pub(super) fn fragment() -> Vec<u8> {
    let mut seq = super::sequence(150, 7);
    seq.extend(super::sequence(120, 9));
    seq
}

pub(super) fn paired_library(fragment: &[u8], distinct: usize) -> super::super::Reads {
    let mut data = super::reads();
    for n in 0..distinct {
        let mut mate = fragment[120..].to_vec();
        if n > 0 {
            let at = (n * 7) % mate.len();
            mate[at] = if mate[at] == b'A' { b'C' } else { b'A' };
        }
        data.seqs.extend([
            fragment[..150].to_vec(),
            rc(&fragment[..150]),
            mate.clone(),
            rc(&mate),
        ]);
    }
    data
}
