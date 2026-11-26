use super::equivalence::case;
use super::{legacy, pairscan};

#[test]
fn sparse_variants_match_legacy() {
    let (seq, calls, sigs, var) = case(24, 60, 30, 0, 7);
    assert_eq!(
        pairscan::unsupported_pair(&seq, &calls, &sigs, &var, 200),
        legacy::unsupported_pair(&seq, &calls, &sigs, &var, 200)
    );
}

fn agrees(mode: u8, groups: usize) -> bool {
    let (seq, calls, sigs, var) = case(24, 6, groups, mode, 11);
    let span = 200;
    let new = pairscan::unsupported_pair(&seq, &calls, &sigs, &var, span);
    let old = legacy::unsupported_pair(&seq, &calls, &sigs, &var, span);
    assert_eq!(new, old);
    new
}

#[test]
fn late_candidate_support_control() {
    assert!(agrees(2, 20));
}

#[test]
fn early_reference_control() {
    assert!(!agrees(1, 20));
}

#[test]
fn eight_signature_cap_control() {
    assert!(agrees(2, 8));
    assert!(agrees(2, 9));
    assert!(!agrees(3, 20));
}
