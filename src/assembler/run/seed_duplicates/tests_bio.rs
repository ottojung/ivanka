use super::rc;
use super::tests_support::{keep, seq};

#[test]
fn exact_seed_copy_and_reverse_complement_are_suppressed() {
    let major = seq(0x1122_3344, 120);
    let kept = keep(
        &[&major],
        &[major.clone(), rc(&major), seq(0x5566_7788, 120)],
    );
    assert_eq!(
        kept,
        vec![2],
        "only exact or RC-exact seed copies may be removed"
    );
}

#[test]
fn single_snv_minority_strain_is_not_suppressed() {
    let major = seq(0x2211_4433, 120);
    let mut minority = major.clone();
    minority[60] = if minority[60] == b'A' { b'C' } else { b'A' };
    let kept = keep(&[&major], &[major.clone(), minority]);
    assert_eq!(
        kept,
        vec![1],
        "a distinct 1-SNV haplotype is not a duplicate"
    );
}

#[test]
fn recombinant_of_two_seeds_is_not_suppressed() {
    let left = seq(0x9e37_79b9, 120);
    let right = seq(0x1234_5678, 120);
    let recombinant = [&left[..60], &right[60..]].concat();
    let kept = keep(
        &[&left, &right],
        &[left.clone(), right.clone(), recombinant],
    );
    assert_eq!(
        kept,
        vec![2],
        "a mosaic of two seeds is a distinct molecule"
    );
}
