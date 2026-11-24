use super::support::hits;
use super::{count, K};

#[test]
fn pair_cap_is_80000_and_generation_does_not_wrap() {
    let map = hits(&[(b'T', vec![(0, 0), (0, 2)])]);
    let contigs = vec![vec![b'T'; K + 4]];
    let mut seqs = Vec::with_capacity(4 * 80_001);
    for _ in 0..80_001 {
        seqs.push(vec![b'T'; K]);
        seqs.push(vec![]);
        seqs.push(vec![b'T'; K]);
        seqs.push(vec![]);
    }
    let stats = count(&contigs, &super::support::reads(seqs), &map);
    assert_eq!(stats.pair_masks.len(), 80_000);
    assert!(stats.pair_masks.iter().all(|&m| m == 1));
    assert_eq!(stats.pairs, vec![80_000]);
    assert_eq!(stats.depth[0][0], 80_000);
    assert_eq!(stats.depth[0][2], 80_000);
}
