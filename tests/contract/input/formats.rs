use super::{fixture, Fixture};

#[test]
fn casava_mates_with_matching_ids_are_accepted() {
    let case = Fixture::new();
    let r1 = case.write("r1.fq", b"@id 1:N:0:sample\nACGT\n+\n!!!!\n");
    let r2 = case.write("r2.fq", b"@id 2:N:0:sample\nTGCA\n+\n!!!!\n");
    let result = case.run_paths(&r1, &r2, &[]);
    assert!(!result.status.success());
    let error = String::from_utf8_lossy(&result.stderr);
    assert!(error.contains("no supported contigs"), "{error}");
    assert!(!error.contains("read-pair IDs"));
}

#[test]
fn plain_matching_ids_are_accepted() {
    let case = Fixture::new();
    let r1 = case.write("r1.fq", b"@id\nACGT\n+\n!!!!\n");
    let r2 = case.write("r2.fq", b"@id\nTGCA\n+\n!!!!\n");
    let result = case.run_paths(&r1, &r2, &[]);
    assert!(!result.status.success());
    let error = String::from_utf8_lossy(&result.stderr);
    assert!(error.contains("no supported contigs"), "{error}");
    assert!(!error.contains("read-pair IDs"));
}

#[test]
fn lowercase_fastq_bases_match_uppercase_assembly() {
    let case = Fixture::new();
    let mut paths = Vec::new();
    for mate in 1..=2 {
        let data = std::fs::read_to_string(fixture(&format!("a_R{mate}.fastq"))).unwrap();
        let normalized = data
            .lines()
            .enumerate()
            .map(|(i, s)| {
                if i % 4 == 1 {
                    s.to_ascii_lowercase()
                } else {
                    s.to_string()
                }
            })
            .collect::<Vec<_>>()
            .join("\n")
            + "\n";
        paths.push(case.write(&format!("r{mate}.fastq"), normalized.as_bytes()));
    }
    assert!(case.run_paths(&paths[0], &paths[1], &[]).status.success());
    assert_eq!(
        case.output(),
        std::fs::read(fixture("a_expected.fa")).unwrap()
    );
}
