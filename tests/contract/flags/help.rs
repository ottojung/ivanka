use super::command;

#[test]
fn help_prints_supported_switches() {
    let output = command().arg("--help").output().unwrap();
    assert!(output.status.success());
    let text = String::from_utf8(output.stdout).unwrap();
    for flag in [
        "--reads1",
        "--reads2",
        "--output",
        "--seeds",
        "--max-pairs",
        "--unphased-snv-audit",
    ] {
        assert!(text.contains(flag), "{flag}");
    }
}

#[test]
fn rejects_unknown_flag() {
    assert!(!command()
        .arg("--inexistent")
        .output()
        .unwrap()
        .status
        .success());
}

#[test]
fn requires_output_path() {
    assert!(!command()
        .args(["--reads1", "a", "--reads2", "b"])
        .output()
        .unwrap()
        .status
        .success());
}

#[test]
fn requires_both_mates() {
    assert!(!command()
        .args(["--output", "/tmp/no-output", "--reads1", "a"])
        .output()
        .unwrap()
        .status
        .success());
}
