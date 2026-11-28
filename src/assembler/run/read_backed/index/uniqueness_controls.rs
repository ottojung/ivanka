//! Negative controls: legitimate overlap, clonal phase and distant strains
//! must not be reported as a repeated graph path.

use super::fixtures::{diverge, genome};
use super::uniqueness::repeated_path;

#[test]
fn overlapping_contigs_are_preserved() {
    let first = genome(5000, 41);
    let second = [&first[2000..], &genome(1000, 43)[..], &[]].concat();
    assert!(repeated_path(&first).is_none());
    assert!(repeated_path(&second).is_none());
}

#[test]
fn clonal_short_repeat_is_preserved() {
    let mut contig = genome(5000, 51);
    let repeat = genome(150, 53);
    contig.extend_from_slice(&repeat);
    contig.extend_from_slice(&repeat);
    assert!(repeated_path(&contig).is_none());
}

#[test]
fn strongly_diverged_segments_are_not_merged() {
    let region = genome(4000, 61);
    let mut contig = region.clone();
    contig.extend_from_slice(&diverge(&region, 30, 67));
    assert!(repeated_path(&contig).is_none());
}
