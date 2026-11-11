use super::support::Fixture;

fn assert_bad_pair(r1: &[u8], r2: &[u8]) {
    let case = Fixture::new();
    let first = case.write("r1.fastq", r1);
    let second = case.write("r2.fastq", r2);
    assert!(!case.run_paths(&first, &second, &[]).status.success());
}

#[test]
fn rejects_different_pair_identifiers() {
    assert_bad_pair(b"@one/1\nACGT\n+\n!!!!\n", b"@two/2\nACGT\n+\n!!!!\n");
}

#[test]
fn rejects_unequal_mate_counts() {
    assert_bad_pair(b"@one/1\nACGT\n+\n!!!!\n", b"");
}

#[test]
fn rejects_swapped_mate_designators() {
    assert_bad_pair(b"@same/2\nACGT\n+\n!!!!\n", b"@same/1\nACGT\n+\n!!!!\n");
}

#[test]
fn rejects_missing_quality_bases() {
    assert_bad_pair(b"@same/1\nACGT\n+\n!!!\n", b"@same/2\nACGT\n+\n!!!!\n");
}

#[test]
fn rejects_missing_fastq_sequence() {
    assert_bad_pair(b"@same/1\n", b"@same/2\nACGT\n+\n!!!!\n");
}

#[test]
fn rejects_invalid_fastq_separator() {
    assert_bad_pair(b"@same/1\nACGT\n-\n!!!!\n", b"@same/2\nACGT\n+\n!!!!\n");
}

#[test]
fn rejects_invalid_fastq_header() {
    assert_bad_pair(b"same/1\nACGT\n+\n!!!!\n", b"@same/2\nACGT\n+\n!!!!\n");
}
