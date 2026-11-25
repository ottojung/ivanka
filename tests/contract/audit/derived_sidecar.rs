use super::Fixture;

// The pinned MiCall invocation supplies --output but no audit flag. The
// ordinary run must still leave an inspectable, output-derived sidecar.
#[test]
fn ordinary_invocation_emits_output_derived_sidecar() {
    let case = Fixture::new();
    assert!(case.run("a", &[]).status.success());
    let sidecar = case.path("output.fasta.snv_audit.tsv");
    let text = std::fs::read_to_string(&sidecar).unwrap();
    assert!(text.starts_with("#schema=ivanka.unphased_snv_candidates.v1\n"));
    assert!(text.contains("ordinary_micall_fasta_unchanged=true"));
}

#[test]
fn explicit_audit_flag_does_not_also_write_derived_sidecar() {
    let case = Fixture::new();
    let audit = case.path("audit.tsv");
    assert!(case
        .run("a", &["--unphased-snv-audit", audit.to_str().unwrap()])
        .status
        .success());
    assert!(audit.exists());
    assert!(!case.path("output.fasta.snv_audit.tsv").exists());
}
