use std::path::Path;
use std::process::Command;

pub fn run(dir: &Path) -> String {
    let output = Command::new(env!("CARGO_BIN_EXE_ivanka"))
        .env_clear()
        .arg("--reads1")
        .arg(dir.join("R1.fastq"))
        .arg("--reads2")
        .arg(dir.join("R2.fastq"))
        .arg("--output")
        .arg(dir.join("out.fa"))
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "ivanka failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    std::fs::read_to_string(dir.join("out.fa")).unwrap()
}

pub fn sequence(fasta: &str) -> String {
    fasta
        .lines()
        .filter(|line| !line.starts_with('>'))
        .collect()
}

/// Orientation is arbitrary, so accept either strand as a read-derived match.
pub fn matches_contig(output: &str, source: &str) -> bool {
    let contig = sequence(output);
    if contig.len() < 150 {
        return false;
    }
    source.contains(&contig) || source.contains(&super::support::reverse(&contig))
}
