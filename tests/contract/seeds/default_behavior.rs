use super::{fixture, Fixture};

#[test]
fn repeated_direct_invocations_are_byte_identical() {
    let seed = fixture("a_seeds.fasta");
    let seed = seed.to_str().unwrap();
    let first = Fixture::new();
    let second = Fixture::new();
    assert!(first.run("a", &["--seeds", seed]).status.success());
    assert!(second.run("a", &["--seeds", seed]).status.success());
    assert_eq!(first.output(), second.output());
}

#[test]
fn caller_seed_file_survives_suppression_and_empty_output_exits_zero() {
    let case = Fixture::new();
    let frozen = std::fs::read(fixture("a_expected.fa")).unwrap();
    let native = frozen
        .split(|&byte| byte == b'>')
        .nth(1)
        .unwrap()
        .split(|&byte| byte == b'\n')
        .skip(1)
        .flatten()
        .copied()
        .collect::<Vec<u8>>();
    let seed = case.write(
        "native_seed.fa",
        &[b">native\n".as_slice(), native.as_slice(), b"\n".as_slice()].concat(),
    );
    let before = std::fs::read(&seed).unwrap();
    let run = case.run("a", &["--seeds", seed.to_str().unwrap()]);
    assert!(run.status.success(), "a valid empty FASTA must exit 0");
    assert!(case.output().is_empty());
    assert_eq!(
        std::fs::read(&seed).unwrap(),
        before,
        "the caller retains its seed input"
    );
}
