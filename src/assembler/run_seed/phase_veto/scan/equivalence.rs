use super::{legacy, pairscan};

type Case = (Vec<u8>, Vec<Vec<(usize, u8)>>, Vec<u32>, Vec<usize>);

// Deterministic read-derived calls: no reference, panel, truth or score.
// mode 0 = mixed alt, 1 = all reference, 2 = alt only in the last 8 groups,
// 3 = reference first then alt.
pub(super) fn case(nv: usize, gap: usize, groups: usize, mode: u8, seed: u64) -> Case {
    let var: Vec<usize> = (0..nv).map(|k| 12 + k * gap).collect();
    let seq = vec![b'A'; 40 + nv * gap];
    let mut calls = Vec::new();
    let mut sigs = Vec::new();
    let mut s = seed;
    for g in 0..groups {
        s ^= s << 13;
        s ^= s >> 7;
        s ^= s << 17;
        let alt = match mode {
            0 => (s & 3) != 0,
            1 => false,
            2 => g + 8 >= groups,
            _ => g >= groups / 2,
        };
        let group = if mode == 2 && g + 8 < groups {
            Vec::new()
        } else {
            var.iter()
                .enumerate()
                .map(|(k, &p)| (p, if alt && (k + g) % 3 != 0 { b'C' } else { b'A' }))
                .collect()
        };
        calls.push(group);
        sigs.push(g as u32 + 1);
    }
    (seq, calls, sigs, var)
}

#[test]
fn dense_long_sequence_matches_legacy() {
    for (nv, gap, span, groups) in [(60usize, 3usize, 50usize, 40usize), (120, 2, 15, 60)] {
        let (seq, calls, sigs, var) = case(nv, gap, groups, 0, 39);
        assert_eq!(
            pairscan::unsupported_pair(&seq, &calls, &sigs, &var, span),
            legacy::unsupported_pair(&seq, &calls, &sigs, &var, span)
        );
    }
}
