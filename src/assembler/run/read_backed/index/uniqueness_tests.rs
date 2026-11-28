//! Positive and legitimate-diversity controls for repeated-path detection.

use super::fixtures::{diverge, genome};
use super::uniqueness::repeated_path;

#[test]
fn duplicate_traversal_is_flagged() {
    let region = genome(4000, 11);
    let second = diverge(&region, 8, 13);
    let mut contig = region;
    contig.extend_from_slice(&second);
    contig.extend_from_slice(&genome(1500, 17));
    let (score, first, repeat) = repeated_path(&contig).expect("duplicate traversal flagged");
    assert!(score >= 250);
    assert_eq!(repeat - first, 4000);
}

#[test]
fn separate_minority_is_preserved() {
    let dominant = genome(5000, 21);
    let minority = diverge(&dominant, 15, 23);
    assert!(repeated_path(&dominant).is_none());
    assert!(repeated_path(&minority).is_none());
}

#[test]
fn recombinant_mosaic_is_preserved() {
    let left = genome(4000, 31);
    let right = genome(4000, 37);
    let mut mosaic = left[..2000].to_vec();
    mosaic.extend_from_slice(&right[2000..]);
    assert!(repeated_path(&mosaic).is_none());
}
