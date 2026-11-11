use super::support::{fixture, Fixture};

#[test]
fn assembled_a_matches_frozen_release() {
    let case = Fixture::new();
    assert!(case.run("a", &[]).status.success());
    assert_eq!(
        case.output(),
        std::fs::read(fixture("a_expected.fa")).unwrap()
    );
}

#[test]
fn assembled_b_matches_frozen_release() {
    let case = Fixture::new();
    assert!(case.run("b", &[]).status.success());
    assert_eq!(
        case.output(),
        std::fs::read(fixture("b_expected.fa")).unwrap()
    );
}

#[test]
fn repeated_runs_produce_identical_fasta() {
    let first = Fixture::new();
    let second = Fixture::new();
    assert!(first.run("a", &[]).status.success());
    assert!(second.run("a", &[]).status.success());
    assert_eq!(first.output(), second.output());
}

#[test]
fn one_contig_cap_keeps_the_dominant_assembly() {
    let case = Fixture::new();
    assert!(case.run("a", &["--max-contigs", "1"]).status.success());
    assert_eq!(
        case.output(),
        std::fs::read(fixture("a_expected.fa")).unwrap()
    );
}

#[test]
fn no_reads_and_no_seeds_produce_empty_fasta() {
    let case = Fixture::new();
    assert!(case.run("a", &["--max-pairs", "0"]).status.success());
    assert!(case.output().is_empty());
}
