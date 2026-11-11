use super::*;
#[test]
fn audit_preflight_protects_originals() {
    let old = std::env::temp_dir().join(format!("ivanka_audit_{}_preflight", std::process::id()));
    let _ = std::fs::create_dir(&old);
    let input = old.join("input.fastq");
    std::fs::write(&input, "immutable").unwrap();
    let path = input.to_str().unwrap();
    assert!(validate_audit(Some(path), None, None, "out.fasta", Some(path)).is_err());
    assert!(validate_audit(
        Some(path),
        None,
        None,
        "out.fasta",
        Some(old.join("new.tsv").to_str().unwrap())
    )
    .is_err());
    assert!(validate_audit(Some(path), None, None, "out.fasta", None).is_ok());
    std::fs::remove_file(input).unwrap();
    std::fs::remove_dir(old).unwrap();
}
