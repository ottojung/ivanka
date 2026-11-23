use super::{fixture, Fixture};

#[test]
fn pass_through_caller_seeds_when_no_original_reads_are_used() {
    let case = Fixture::new();
    let seed = fixture("a_seeds.fasta");
    let result = case.run(
        "a",
        &[
            "--max-pairs",
            "0",
            "--max-contigs",
            "6",
            "--seeds",
            seed.to_str().unwrap(),
        ],
    );
    assert!(result.status.success());
    assert_eq!(
        case.output().split(|&base| base == b'>').count(),
        3,
        "with zero loaded read pairs, both protected source seeds must survive"
    );
}

#[test]
fn reject_nonstandard_adapter_specific_flag() {
    let case = Fixture::new();
    let result = case.run("a", &["--exclude-supplied-seed-duplicates"]);
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("unknown/incomplete argument"));
}

#[test]
fn unseeded_no_original_reads_remains_empty() {
    let case = Fixture::new();
    let result = case.run("a", &["--max-pairs", "0", "--max-contigs", "6"]);
    assert!(result.status.success());
    assert!(case.output().is_empty());
}
