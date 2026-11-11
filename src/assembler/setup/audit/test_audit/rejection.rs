use super::*;
#[test]
fn unobserved_and_multi_snv_sequences_never_become_nodes() {
    let (base, alt, _) = example();
    let path = output_path("missing");
    let count = write_snv_audit(
        &path,
        &[(alt.clone(), 150)],
        &[base.clone()],
        &HashMap::new(),
        kmer,
    )
    .unwrap();
    assert_eq!(count, 0);
    std::fs::remove_file(path).unwrap();
    let mut wrong = alt.clone();
    wrong[145] = if wrong[145] == b'A' { b'C' } else { b'A' };
    let path = output_path("two");
    let mut counts = HashMap::new();
    for k in wrong.windows(31).filter_map(kmer) {
        counts.insert(k, 10);
    }
    assert_eq!(
        write_snv_audit(&path, &[(wrong, 150)], &[base], &counts, kmer).unwrap(),
        0
    );
    std::fs::remove_file(path).unwrap();
}
