use super::Fixture;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

pub fn fixture(name: &str) -> PathBuf {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures");
    if name.ends_with("_expected.fa") || name.ends_with("_default_read_backed.fa") {
        root.join("expected").join(name)
    } else {
        root.join(name)
    }
}

pub fn command() -> Command {
    let mut cmd = Command::new(env!("CARGO_BIN_EXE_ivanka"));
    cmd.env_clear();
    cmd
}

impl Fixture {
    pub fn run(&self, sample: &str, options: &[&str]) -> Output {
        self.run_paths(
            &fixture(&format!("{sample}_R1.fastq")),
            &fixture(&format!("{sample}_R2.fastq")),
            options,
        )
    }

    pub fn run_paths(&self, r1: &Path, r2: &Path, options: &[&str]) -> Output {
        command()
            .arg("--reads1")
            .arg(r1)
            .arg("--reads2")
            .arg(r2)
            .arg("--output")
            .arg(self.path("output.fasta"))
            .args(["--max-pairs", "260", "--max-contigs", "2"])
            .args(options)
            .output()
            .unwrap()
    }
}
