use super::{fixture, Fixture};

#[test]
fn protected_read_derived_seed_matches_frozen_release() {
    let case = Fixture::new();
    let seed = fixture("a_seeds.fasta");
    assert!(case
        .run(
            "a",
            &["--max-pairs", "0", "--seeds", seed.to_str().unwrap()]
        )
        .status
        .success());
    assert_eq!(
        case.output(),
        std::fs::read(fixture("a_seeded_expected.fa")).unwrap()
    );
}

#[test]
fn supplied_seed_is_extended_with_its_original_reads() {
    let case = Fixture::new();
    let seed = fixture("a_seeds.fasta");
    assert!(case
        .run("a", &["--seeds", seed.to_str().unwrap()])
        .status
        .success());
    assert_eq!(
        case.output(),
        std::fs::read(fixture("a_seeded_full_expected.fa")).unwrap()
    );
}
