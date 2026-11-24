use super::{fixture, Fixture};

fn records(fasta: &[u8]) -> Vec<Vec<u8>> {
    fasta
        .split(|&byte| byte == b'>')
        .skip(1)
        .map(|record| {
            record
                .split(|&byte| byte == b'\n')
                .skip(1)
                .flatten()
                .copied()
                .collect()
        })
        .collect()
}

#[test]
fn direct_caller_with_reads_loses_the_exact_seed_contig() {
    let frozen = std::fs::read(fixture("a_expected.fa")).unwrap();
    let native = records(&frozen).remove(0);
    let case = Fixture::new();
    let seed = case.write(
        "native_seed.fa",
        &[b">native\n".as_slice(), native.as_slice(), b"\n".as_slice()].concat(),
    );
    let reads = case.run("a", &["--seeds", seed.to_str().unwrap()]);
    assert!(reads.status.success());
    assert!(String::from_utf8_lossy(&reads.stderr)
        .contains("IVANKA_NATIVE_SUPPLIED_SEED_DUPLICATES removed=1"));
    assert!(
        !records(&case.output()).contains(&native),
        "standalone caller's exact seed contig is absent once reads are admitted"
    );
    let empty = case.run(
        "a",
        &["--max-pairs", "0", "--seeds", seed.to_str().unwrap()],
    );
    assert!(empty.status.success());
    assert!(
        records(&case.output()).contains(&native),
        "without admitted reads the unchanged seed is emitted"
    );
}
