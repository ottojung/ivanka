use super::{fixture, Fixture};

#[test]
fn audit_never_overwrites_existing_output() {
    let case = Fixture::new();
    let audit = case.write("audit.tsv", b"keep-me");
    assert!(!case
        .run("a", &["--unphased-snv-audit", audit.to_str().unwrap()])
        .status
        .success());
    assert_eq!(std::fs::read(audit).unwrap(), b"keep-me");
}

#[test]
fn audit_path_cannot_alias_contig_fasta() {
    let case = Fixture::new();
    let audit = case.path("output.fasta");
    assert!(!case
        .run("a", &["--unphased-snv-audit", audit.to_str().unwrap()])
        .status
        .success());
}

#[test]
fn audit_cannot_modify_original_input_directory() {
    let case = Fixture::new();
    let target = fixture("unexpected_originals.tsv");
    assert!(!case
        .run("a", &["--unphased-snv-audit", target.to_str().unwrap()])
        .status
        .success());
    assert!(!target.exists());
}
