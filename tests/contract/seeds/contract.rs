use super::{fixture, Fixture};
use std::path::PathBuf;

fn dominant_seed(case: &Fixture) -> PathBuf {
    let f = std::fs::read_to_string(fixture("a_expected.fa")).unwrap();
    let rec = f.split('>').nth(1).unwrap();
    let seq: String = rec.lines().skip(1).collect();
    case.write("dominant.fa", format!(">d\n{seq}\n").as_bytes())
}

#[test]
fn adapter_and_standalone_invocations_are_byte_identical() {
    let adapter = Fixture::new();
    let standalone = Fixture::new();
    let s = fixture("a_seeds.fasta");
    let s = s.to_str().unwrap();
    assert!(adapter.run("a", &["--seeds", s]).status.success());
    assert!(standalone.run("a", &["--seeds", s]).status.success());
    assert_eq!(adapter.output(), standalone.output());
}

#[test]
fn exact_dominant_seed_with_admitted_reads_is_a_valid_empty_fasta() {
    let case = Fixture::new();
    let s = dominant_seed(&case);
    let s = s.to_str().unwrap();
    let r = case.run("a", &["--max-contigs", "1", "--seeds", s]);
    assert!(r.status.success());
    assert!(String::from_utf8_lossy(&r.stderr)
        .contains("IVANKA_NATIVE_SUPPLIED_SEED_DUPLICATES removed=1"));
    assert!(case.output().is_empty());
}

#[test]
fn only_read_admission_changes_the_fate_of_an_exact_seed() {
    let case = Fixture::new();
    let s = dominant_seed(&case);
    let s = s.to_str().unwrap();
    assert!(case
        .run("a", &["--max-contigs", "1", "--seeds", s])
        .status
        .success());
    assert!(case.output().is_empty());
    let no_reads = case.run(
        "a",
        &["--max-pairs", "0", "--max-contigs", "1", "--seeds", s],
    );
    assert!(no_reads.status.success());
    assert_eq!(case.output().split(|&b| b == b'>').count() - 1, 1);
}
