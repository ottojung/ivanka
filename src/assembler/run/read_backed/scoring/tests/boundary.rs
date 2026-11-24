use super::support::hits;
use super::{count, K};

#[test]
fn sixteen_candidate_mask_boundary_is_preserved() {
    let locations: Vec<(usize, usize)> = (0..16).flat_map(|c| [(c, 0), (c, 1)]).collect();
    let map = hits(&[(b'G', locations)]);
    let contigs: Vec<Vec<u8>> = (0..16).map(|_| vec![b'G'; K + 2]).collect();
    let seqs = vec![vec![b'G'; K], vec![], vec![b'G'; K], vec![]];
    let stats = count(&contigs, &super::support::reads(seqs), &map);
    assert_eq!(stats.pair_masks, vec![0xffff]);
    assert!(stats.pairs.iter().all(|&n| n == 1));
    assert!(stats.depth.iter().all(|d| d[0] == 1 && d[1] == 1));
}
