//! A single variant produces several overlapping private 31-mers from one
//! physical locus. These fixtures enter scoring as real mate records to show
//! that the two-locus mask gate is met by overlapping windows.

use super::super::super::{index, ranking};
use super::super::count;
use super::support::{rc, reads, sequence, tiled};

#[test]
fn one_substitution_yields_an_exclusive_pair_mask() {
    let mut a = sequence(160, 11);
    let mut b = a.clone();
    b[80] = if b[80] == b'A' { b'C' } else { b'A' };
    let contigs = vec![a, b];
    let pair = (contigs[1][50..110].to_vec(), rc(&contigs[1][100..160]));
    let stats = count(&contigs, &reads(&[pair]), &index::build(&contigs));
    assert_eq!(stats.pair_masks, vec![3]);
    // Overlapping windows spanning the one substitution are distinct loci on
    // the candidate, so the >=2 loci gate cannot distinguish them from a
    // genuinely private stretch.
    assert_eq!(stats.exclusive_masks, vec![2]);
}

#[test]
fn private_block_component_is_admitted_from_raw_reads() {
    let a = sequence(400, 7);
    let mut b = a.clone();
    b[100..300].copy_from_slice(&sequence(200, 9));
    let contigs = vec![a.clone(), b.clone()];
    let mut pairs = tiled(&a, 60);
    pairs.extend(tiled(&b, 60));
    let stats = count(&contigs, &reads(&pairs), &index::build(&contigs));
    // The dominant candidate is fixed at 0 so the related path is exercised
    // deterministically; selection itself stays reference-blind.
    assert_eq!(ranking::additional(&contigs, &stats, 0), vec![1]);
}
