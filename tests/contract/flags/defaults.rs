use super::{fixture, Fixture};
use std::process::Command;

#[test]
fn native_seed_limits_default_without_environment() {
    let case = Fixture::new();
    let output = Command::new(env!("CARGO_BIN_EXE_ivanka"))
        .env_remove("IVANKA_BENCH_PRIMARY_SEEDS")
        .env_remove("IVANKA_BENCH_RESCUE_SEEDS")
        .arg("--reads1")
        .arg(fixture("a_R1.fastq"))
        .arg("--reads2")
        .arg(fixture("a_R2.fastq"))
        .args(["--max-pairs", "1"])
        .arg("--output")
        .arg(case.path("default.fa"))
        .output()
        .unwrap();
    assert!(output.status.success());
    assert!(case.path("default.fa").is_file());
    let text = String::from_utf8_lossy(&output.stderr);
    assert!(
        text.contains("IVANKA_SEED_BUDGET primary=50 rescue=20"),
        "{text}"
    );
}
