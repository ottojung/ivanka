use super::{fixture, Fixture};

#[test]
fn second_seed_is_protected_when_quota_permits() {
    let case = Fixture::new();
    let seed = fixture("a_seeds.fasta");
    assert!(case
        .run(
            "a",
            &[
                "--max-pairs",
                "0",
                "--max-contigs",
                "6",
                "--seeds",
                seed.to_str().unwrap()
            ]
        )
        .status
        .success());
    assert_eq!(case.output().split(|&b| b == b'>').count(), 3);
}

#[test]
fn lowercase_seed_is_accepted_as_uppercase() {
    let case = Fixture::new();
    let seed = case.write(
        "lower.fa",
        b">sample\nacgtacgtacgtacgtacgtacgtacgtacgtacgt\n",
    );
    assert!(case
        .run(
            "a",
            &["--max-pairs", "0", "--seeds", seed.to_str().unwrap()]
        )
        .status
        .success());
    assert!(String::from_utf8(case.output())
        .unwrap()
        .contains("ACGTACGT"));
}
