use super::*;
#[test]
fn observed_local_variants_are_unphased_separate_evidence() {
    let (base, alt, counts) = example();
    let path = output_path("supported");
    let count = write_snv_audit(
        &path,
        &[(alt.clone(), 150), (alt.clone(), 140)],
        std::slice::from_ref(&base),
        &counts,
        kmer,
    )
    .unwrap();
    let data = std::fs::read_to_string(&path).unwrap();
    assert_eq!(count, 1);
    assert!(data.contains("phasing=unidentified"));
    assert!(data.contains("phred_unchecked=true"));
    assert!(data.contains("independent_dna_molecules=false"));
    assert!(data.contains("1\t300\t150\t"));
    assert!(!data.contains(&String::from_utf8(base).unwrap()));
    assert_eq!(
        std::fs::metadata(&path).unwrap().permissions().mode() & 0o777,
        0o600
    );
    assert!(write_snv_audit(&path, &[], &[], &counts, kmer).is_err());
    assert_eq!(
        data.lines()
            .filter(|line| line.starts_with("1\t300\t150"))
            .count(),
        1
    );
    std::fs::remove_file(path).unwrap();
}
