use super::{fixture, Fixture};
use std::process::{Command, Output};

/// Production and qualification use exactly three flags and no environment.
fn run(sample: &str, environment: &[(&str, &str)]) -> (Fixture, Output) {
    let case = Fixture::new();
    let mut command = Command::new(env!("CARGO_BIN_EXE_ivanka"));
    command.env_clear();
    for &(name, value) in environment {
        command.env(name, value);
    }
    let result = command
        .arg("--reads1")
        .arg(fixture(&format!("{sample}_R1.fastq")))
        .arg("--reads2")
        .arg(fixture(&format!("{sample}_R2.fastq")))
        .arg("--output")
        .arg(case.path("output.fasta"))
        .output()
        .unwrap();
    (case, result)
}

#[test]
fn normal_invocation_matches_frozen_python_read_backed_fasta() {
    for sample in ["a", "b"] {
        let (case, result) = run(sample, &[]);
        assert!(result.status.success());
        assert_eq!(
            case.output(),
            std::fs::read(fixture(&format!("{sample}_default_read_backed.fa"))).unwrap()
        );
        assert!(String::from_utf8_lossy(&result.stderr).contains("IVANKA_READ_BACKED_SELECTION"));
    }
}

#[test]
fn environment_cannot_change_the_normal_assembly() {
    let (baseline, _) = run("a", &[]);
    let (override_attempt, result) = run(
        "a",
        &[
            ("IVANKA_BENCH_PRIMARY_SEEDS", "1"),
            ("IVANKA_BENCH_RESCUE_SEEDS", "1"),
            ("IVANKA_POSTSELECT_CONTIGS", "999"),
            ("IVANKA_READ_BACKED_TILE_SPAN", "0"),
        ],
    );
    assert!(result.status.success());
    assert_eq!(baseline.output(), override_attempt.output());
}
