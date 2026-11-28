//! Raw-read diversity controls: signature count is a lower bound, not dedup.

use super::super::super::{index, ranking};
use super::super::count;
use super::sig_count;
use super::support::{rc, reads, sequence, tiled};

#[test]
fn pcr_identical_pairs_do_not_admit_single_locus_component() {
    let a = sequence(400, 7);
    let mut b = a.clone();
    b[200] = if b[200] == b'A' { b'C' } else { b'A' };
    let contigs = vec![a.clone(), b.clone()];
    let mut pairs = tiled(&a, 60);
    pairs.extend(tiled(&b, 60));
    let dup = (b[170..230].to_vec(), rc(&b[170..230]));
    pairs.extend(std::iter::repeat_n(dup, 30));
    let stats = count(&contigs, &reads(&pairs), &index::build(&contigs));
    assert_eq!(sig_count(&stats, 1), 1);
    assert!(ranking::additional(&contigs, &stats, 0).is_empty());
}

#[test]
fn distinct_fragments_can_admit_genuine_single_locus_strain() {
    let a = sequence(400, 11);
    let mut b = a.clone();
    b[200] = if b[200] == b'A' { b'C' } else { b'A' };
    let contigs = vec![a.clone(), b.clone()];
    let mut pairs = tiled(&a, 60);
    pairs.extend(tiled(&b, 60));
    let stats = count(&contigs, &reads(&pairs), &index::build(&contigs));
    assert!(sig_count(&stats, 1) >= 2);
    assert_eq!(ranking::additional(&contigs, &stats, 0), vec![1]);
}

#[test]
fn disjoint_private_block_and_shared_only_controls() {
    let a = sequence(400, 7);
    let mut b = a.clone();
    b[100..300].copy_from_slice(&sequence(200, 9));
    let contigs = vec![a.clone(), b.clone()];
    let mut pairs = tiled(&a, 60);
    pairs.extend(tiled(&b, 60));
    let shared = reads(&tiled(&a, 60));
    let shared_stats = count(&contigs, &shared, &index::build(&contigs));
    assert!(ranking::additional(&contigs, &shared_stats, 0).is_empty());
    let stats = count(&contigs, &reads(&pairs), &index::build(&contigs));
    assert!(sig_count(&stats, 1) >= 20);
    assert_eq!(ranking::additional(&contigs, &stats, 0), vec![1]);
}
