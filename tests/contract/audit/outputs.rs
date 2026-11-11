use super::{fixture, Fixture};

#[test]
fn audit_does_not_change_ordinary_fasta() {
    let case = Fixture::new();
    let audit = case.path("audit.tsv");
    assert!(case
        .run("a", &["--unphased-snv-audit", audit.to_str().unwrap()])
        .status
        .success());
    assert_eq!(
        case.output(),
        std::fs::read(fixture("a_expected.fa")).unwrap()
    );
}

#[test]
fn audit_has_explicit_unphased_schema() {
    let case = Fixture::new();
    let audit = case.path("audit.tsv");
    assert!(case
        .run("a", &["--unphased-snv-audit", audit.to_str().unwrap()])
        .status
        .success());
    let text = std::fs::read_to_string(&audit).unwrap();
    assert!(text.starts_with("#schema=ivanka.unphased_snv_candidates.v1\n"));
    assert!(text.contains("independent_dna_molecules=false"));
}

#[test]
fn audit_file_uses_private_permissions() {
    use std::os::unix::fs::PermissionsExt;
    let case = Fixture::new();
    let audit = case.path("audit.tsv");
    assert!(case
        .run("a", &["--unphased-snv-audit", audit.to_str().unwrap()])
        .status
        .success());
    assert_eq!(
        std::fs::metadata(audit).unwrap().permissions().mode() & 0o777,
        0o600
    );
}
