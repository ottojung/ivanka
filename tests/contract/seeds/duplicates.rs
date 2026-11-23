use super::{fixture, Fixture};

#[test]
fn optionally_skip_exact_caller_seed_outputs_without_discarding_pipeline() {
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
            "--exclude-supplied-seed-duplicates",
        ],
    );
    assert!(result.status.success());
    assert!(
        case.output().is_empty(),
        "protected seed copies must be omitted"
    );
}

#[test]
fn exclusion_requires_a_supplied_seed_input() {
    let case = Fixture::new();
    let result = case.run("a", &["--exclude-supplied-seed-duplicates"]);
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("requires --seeds"));
}
