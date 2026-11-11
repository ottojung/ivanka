use super::{canonical_kmer, K};
mod oracle;
use super::rescue_rank::append_preserving_diversity;

#[test]
fn linear_cover_matches_original_across_ambiguous_and_phased_paths() {
    let mut rng = 0x8a3c_0c57_2f6d_4b19u64;
    let mut next = || {
        rng ^= rng << 13;
        rng ^= rng >> 7;
        rng ^= rng << 17;
        rng
    };
    for case in 0..600 {
        let n = 2 + (next() % 8) as usize;
        let template = (0..150)
            .map(|_| b"ACGTN"[(next() % 5) as usize])
            .collect::<Vec<_>>();
        let mut v = (0..n)
            .map(|i| {
                let len = 30 + (next() % 90) as usize;
                if i % 3 == 0 {
                    template[..len].to_vec()
                } else {
                    (0..len).map(|_| b"ACGTN"[(next() % 5) as usize]).collect()
                }
            })
            .collect::<Vec<_>>();
        let rescue = if case % 2 == 0 {
            v[(next() % n as u64) as usize].clone()
        } else {
            (0..(30 + (next() % 90) as usize))
                .map(|_| b"ACGTN"[(next() % 5) as usize])
                .collect()
        };
        let cap = if case % 7 == 0 { n + 1 } else { n };
        let protected = (next() % (n as u64 + 1)) as usize;
        let mut expected = v.clone();
        let before = oracle::oracle(&mut expected, rescue.clone(), cap, protected);
        let after = append_preserving_diversity(&mut v, rescue, cap, protected);
        assert_eq!((after, v), (before, expected), "case {case}");
    }
}
