use super::support::Fixture;

#[test]
fn unseeded_low_depth_reports_warning() {
    let case = Fixture::new();
    let result = case.run("a", &["--max-pairs", "1"]);
    assert!(!result.status.success());
    assert!(!case.path("output.fasta").exists());
    assert!(String::from_utf8_lossy(&result.stderr).contains("no supported contigs"));
}

#[test]
fn overly_long_reads_are_not_silently_discarded() {
    let case = Fixture::new();
    let sequence = "A".repeat(65536);
    let record = format!("@pair/1\n{sequence}\n+\n{}\n", "I".repeat(65536));
    let mate = record.replace("@pair/1", "@pair/2");
    let a = case.write("r1.fastq", record.as_bytes());
    let b = case.write("r2.fastq", mate.as_bytes());
    let result = case.run_paths(&a, &b, &["--max-pairs", "1"]);
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("65535"));
}
