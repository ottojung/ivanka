use super::{reads, sequence};

fn library(support_pairs: usize, total_pairs: usize, fragment: &[u8]) -> Vec<Vec<u8>> {
    let mut data = reads();
    for n in 0..(total_pairs - support_pairs) {
        let a = sequence(60, 5000 + n as u64);
        let b = sequence(60, 20000 + n as u64);
        data.seqs.extend([a.clone(), a.clone(), b.clone(), b]);
    }
    for n in 0..support_pairs {
        let mate = sequence(60, 1000 + n as u64);
        data.seqs
            .extend([fragment.to_vec(), fragment.to_vec(), mate.clone(), mate]);
    }
    data.seqs
}

#[test]
fn exactly_one_percent_of_distinct_pairs_is_eligible() {
    let fragment = sequence(60, 2);
    let mut data = reads();
    data.seqs = library(15, 1500, &fragment);
    let ranked = super::super::support::ranked(&data);
    assert!(ranked
        .iter()
        .any(|(seq, _)| seq.as_slice() == fragment.as_slice()));
}

#[test]
fn just_below_one_percent_of_distinct_pairs_is_ineligible() {
    let fragment = sequence(60, 2);
    let mut data = reads();
    data.seqs = library(15, 1516, &fragment);
    let ranked = super::super::support::ranked(&data);
    assert!(!ranked
        .iter()
        .any(|(seq, _)| seq.as_slice() == fragment.as_slice()));
}

#[test]
fn denominator_includes_pairs_beyond_any_fixed_scan_cap() {
    let fragment = sequence(60, 2);
    let mut data = reads();
    data.seqs = library(810, 80_810, &fragment);
    let ranked = super::super::support::ranked(&data);
    assert!(ranked
        .iter()
        .any(|(seq, _)| seq.as_slice() == fragment.as_slice()));
}
