use super::fixtures::{add, paired, rc};
use super::{reads, sequence};

#[test]
fn identical_mates_within_a_pair_count_once() {
    let fragment = sequence(60, 2);
    let mut data = reads();
    data.seqs = paired(&fragment, &fragment, 1000);
    assert!(super::super::support::ranked(&data).is_empty());
}

#[test]
fn reverse_complement_mates_share_one_identity() {
    let fragment = sequence(60, 2);
    let mate = rc(&fragment);
    let mut data = reads();
    data.seqs = paired(&fragment, &mate, 1000);
    assert!(super::super::support::ranked(&data).is_empty());
}

#[test]
fn reverse_complement_observations_merge_support() {
    let fragment = sequence(60, 2);
    let reversed = rc(&fragment);
    let mut data = reads();
    add(&mut data, &fragment, 100, 15);
    add(&mut data, &reversed, 200, 15);
    let ranked = super::super::support::ranked(&data);
    let found = ranked
        .iter()
        .find(|(seq, _)| seq.as_slice() == fragment.as_slice());
    assert_eq!(found.unwrap().1, 30);
}

#[test]
fn ambiguous_read_without_canonical_kmer_is_ineligible() {
    let fragment = vec![b'N'; 60];
    let mut data = reads();
    add(&mut data, &fragment, 100, 20);
    assert!(super::super::support::ranked(&data).is_empty());
}
