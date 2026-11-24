use super::{index, Reads, K};
use std::cell::{Cell, RefCell};
use std::collections::HashMap;

pub(super) fn lcg(state: &mut u64) -> u8 {
    *state = state
        .wrapping_mul(6_364_136_223_846_793_005)
        .wrapping_add(1);
    [b'A', b'C', b'G', b'T'][((*state >> 33) & 3) as usize]
}

pub(super) fn reads(seqs: Vec<Vec<u8>>) -> Reads {
    let max_read_len = seqs.iter().map(Vec::len).max().unwrap_or(0);
    Reads {
        seqs,
        index: HashMap::new(),
        seed_counts: HashMap::new(),
        max_read_len,
        overlength_rejections: Cell::new(0),
        overhang_cache: RefCell::new(HashMap::new()),
    }
}

#[test]
fn rolling_matches_pack_and_original_start_parity() {
    let mut state = 0x0bad_c0de_1234_5678u64;
    let seq: Vec<u8> = (0..400)
        .map(|i| if i % 47 == 0 { b'N' } else { lcg(&mut state) })
        .collect();
    let valid = |p: usize| {
        seq[p..p + K]
            .iter()
            .all(|b| matches!(b, b'A' | b'C' | b'G' | b'T'))
    };
    let expected: Vec<(usize, u64)> = (0..=seq.len() - K)
        .filter(|&p| valid(p))
        .map(|p| (p, index::pack(&seq[p..p + K]).unwrap()))
        .collect();
    assert_eq!(index::rolling(&seq).collect::<Vec<_>>(), expected);
    let sampled: Vec<u64> = (0..=seq.len() - K)
        .step_by(2)
        .filter(|&p| valid(p))
        .map(|p| index::pack(&seq[p..p + K]).unwrap())
        .collect();
    let even: Vec<u64> = expected
        .iter()
        .filter(|(p, _)| p % 2 == 0)
        .map(|(_, k)| *k)
        .collect();
    assert_eq!(even, sampled);
}
