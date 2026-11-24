use super::rc;
use super::tests_support::{keep, seq};

#[test]
fn partially_overlapping_and_disjoint_contigs_are_not_suppressed() {
    let seed = seq(0xabcd_ef01, 120);
    let overlap = seed[20..100].to_vec();
    let disjoint = seq(0x0bad_c0de, 120);
    let kept = keep(&[&seed], &[seed.clone(), overlap, disjoint]);
    assert_eq!(kept, vec![1, 2], "suppression matches whole sequences only");
}

#[test]
fn reverse_complement_of_a_minority_variant_is_not_suppressed() {
    let major = seq(0xfeed_face, 120);
    let mut minority = major.clone();
    minority[80] = if minority[80] == b'G' { b'T' } else { b'G' };
    let kept = keep(&[&major], &[major.clone(), rc(&major), rc(&minority)]);
    assert_eq!(kept, vec![2], "RC matching is exact, not approximate");
}

#[test]
fn empty_seed_fasta_suppresses_nothing() {
    let first = seq(0x1357_9bdf, 120);
    let second = seq(0x2468_ace0, 120);
    let kept = keep(&[], &[first, second]);
    assert_eq!(kept, vec![0, 1]);
}
