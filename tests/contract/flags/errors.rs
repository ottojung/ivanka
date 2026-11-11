use super::Fixture;

#[test]
fn rejects_zero_contig_limit() {
    let case = Fixture::new();
    assert!(!case.run("a", &["--max-contigs", "0"]).status.success());
}

#[test]
fn rejects_contig_limit_above_one_thousand() {
    let case = Fixture::new();
    assert!(!case.run("a", &["--max-contigs", "1001"]).status.success());
}

#[test]
fn rejects_nonnumeric_pair_limit() {
    let case = Fixture::new();
    assert!(!case.run("a", &["--max-pairs", "NaN"]).status.success());
}

#[test]
fn rejects_flag_without_argument() {
    let case = Fixture::new();
    assert!(!case.run("a", &["--seeds"]).status.success());
}
