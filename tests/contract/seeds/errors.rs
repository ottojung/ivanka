use super::Fixture;

#[test]
fn ambiguous_seed_is_not_emitted() {
    let case = Fixture::new();
    let seed = case.write(
        "ambiguous.fa",
        b">ambiguous\nNNNNACGTACGTACGTACGTACGTACGTACGTACGT\n",
    );
    assert!(case
        .run(
            "a",
            &["--max-pairs", "0", "--seeds", seed.to_str().unwrap()]
        )
        .status
        .success());
    assert!(case.output().is_empty());
}

#[test]
fn malformed_fasta_without_header_is_rejected() {
    let case = Fixture::new();
    let seed = case.write("bad.fa", b"ACGTACGTACGTACGTACGTACGTACGTACGT\n");
    assert!(!case
        .run(
            "a",
            &["--max-pairs", "0", "--seeds", seed.to_str().unwrap()]
        )
        .status
        .success());
}

#[test]
fn empty_seed_file_does_not_create_contigs() {
    let case = Fixture::new();
    let seed = case.write("empty.fa", b"");
    assert!(case
        .run(
            "a",
            &["--max-pairs", "0", "--seeds", seed.to_str().unwrap()]
        )
        .status
        .success());
    assert!(case.output().is_empty());
}
