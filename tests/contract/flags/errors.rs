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

#[test]
fn invalid_seed_budget_is_an_error_not_a_panic() {
    let case = Fixture::new();
    let result = super::super::support::command()
        .env("IVANKA_BENCH_PRIMARY_SEEDS", "not-a-number")
        .arg("--reads1")
        .arg(super::super::support::fixture("a_R1.fastq"))
        .arg("--reads2")
        .arg(super::super::support::fixture("a_R2.fastq"))
        .arg("--output")
        .arg(case.path("out.fasta"))
        .output()
        .unwrap();
    assert!(!result.status.success());
    let stderr = String::from_utf8_lossy(&result.stderr);
    assert!(stderr.contains("IVANKA_BENCH_PRIMARY_SEEDS"), "{stderr}");
    assert!(!stderr.contains("panicked"), "{stderr}");
}
