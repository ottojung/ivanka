use super::*;
#[test]
fn direct_overhang_references_match_original_consensus() {
    let mut state = 0x741e_521c_6349_3d6au64;
    for n in [0, 1, 2, 6, 16, 300] {
        let mut overhangs = Vec::new();
        for _ in 0..n {
            let len = (state as usize) % 105;
            let mut seq = vec![b'A'; len];
            for base in &mut seq {
                state ^= state << 13;
                state ^= state >> 7;
                state ^= state << 17;
                *base = b"ACGTN"[(state % 5) as usize];
            }
            overhangs.push(seq);
        }
        for cov in [0, 1, 2, 6, 12] {
            for ratio in [0, 1, 2, 4] {
                let previous = super::oracle::reference_consensus(&overhangs, cov, ratio, 100);
                assert_eq!(
                    choose_extension(&overhangs, cov, ratio, 100),
                    previous,
                    "count={n} cov={cov} ratio={ratio}"
                );
            }
        }
    }
}
