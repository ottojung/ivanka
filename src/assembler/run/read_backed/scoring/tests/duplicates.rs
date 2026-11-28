//! One physical fragment sequenced more than once is several records, and
//! scoring currently casts one vote per record. These fixtures record that
//! behaviour from raw mates rather than from hand-built Statistics.

use super::super::super::index;
use super::super::count;
use super::support::{rc, reads, sequence};

fn contigs() -> Vec<Vec<u8>> {
    let a = sequence(160, 7);
    let mut b = a.clone();
    b[60..100].copy_from_slice(&sequence(40, 9));
    vec![a, b]
}

#[test]
fn identical_duplicate_pairs_each_cast_an_exclusive_vote() {
    let contigs = contigs();
    let pair = (contigs[1][20..80].to_vec(), rc(&contigs[1][100..160]));
    let stats = count(&contigs, &reads(&vec![pair; 12]), &index::build(&contigs));
    assert_eq!(stats.pair_masks, vec![3; 12]);
    assert_eq!(stats.exclusive_masks, vec![2; 12]);
}

#[test]
fn shared_region_reads_have_no_exclusive_vote() {
    let contigs = contigs();
    let pair = (contigs[0][100..160].to_vec(), rc(&contigs[0][100..160]));
    let stats = count(&contigs, &reads(&[pair]), &index::build(&contigs));
    assert_eq!(stats.pair_masks, vec![3]);
    assert_eq!(stats.exclusive_masks, vec![0]);
}
