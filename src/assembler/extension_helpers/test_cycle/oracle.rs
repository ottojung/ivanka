use super::*;
#[test]
fn cycle_distinct_anchor_count_matches_hashset_oracle() {
    use super::cycle::{repeats, CYCLE_MIN_SPACING};
    use std::collections::HashSet;
    let mut rng = 0x8d7e53c1a91f26b4u64;
    for trial in 0..512 {
        let mut tract = vec![b'A'; CYCLE_MATCH];
        for (i, b) in tract.iter_mut().enumerate() {
            rng ^= rng << 13;
            rng ^= rng >> 7;
            rng ^= rng << 17;
            *b = if trial % 3 == 0 && i % 17 == 0 {
                b'N'
            } else if trial % 7 == 0 {
                b'A'
            } else {
                b"ACGT"[(rng & 3) as usize]
            };
        }
        let mut seq = tract.clone();
        seq.extend(vec![b'G'; CYCLE_MIN_SPACING]);
        let second = seq.len();
        seq.extend_from_slice(&tract);
        let expected = tract
            .windows(31)
            .step_by(32)
            .filter_map(encode)
            .collect::<HashSet<_>>()
            .len()
            >= 8;
        assert_eq!(
            repeats(&seq, 0, second, 31, encode),
            expected,
            "trial {trial}"
        );
    }
}
