use super::support::{fixture, Fixture};

#[test]
fn max_pairs_zero_stops_before_loading_reads() {
    let case = Fixture::new();
    assert!(case.run("a", &["--max-pairs", "0"]).status.success());
    assert!(case.output().is_empty());
}

#[test]
fn max_pairs_one_does_not_form_a_supported_assembly() {
    let case = Fixture::new();
    assert!(case.run("a", &["--max-pairs", "1"]).status.success());
    assert!(case.output().is_empty());
}

#[test]
fn max_pairs_ten_does_not_form_a_supported_assembly() {
    let case = Fixture::new();
    assert!(case.run("a", &["--max-pairs", "10"]).status.success());
    assert!(case.output().is_empty());
}

#[test]
fn larger_contig_budget_does_not_replace_dominant_a() {
    let case = Fixture::new();
    assert!(case.run("a", &["--max-contigs", "16"]).status.success());
    assert_eq!(
        case.output(),
        std::fs::read(fixture("a_expected.fa")).unwrap()
    );
}

#[test]
fn larger_contig_budget_does_not_replace_dominant_b() {
    let case = Fixture::new();
    assert!(case.run("b", &["--max-contigs", "16"]).status.success());
    assert_eq!(
        case.output(),
        std::fs::read(fixture("b_expected.fa")).unwrap()
    );
}
