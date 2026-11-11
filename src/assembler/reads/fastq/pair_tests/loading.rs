use super::*;

#[test]
fn reordered_pairs_fail_during_actual_load() {
    let d = std::env::temp_dir();
    let a = d.join(format!("ivanka-verified-r1-{}.fastq", std::process::id()));
    let b = d.join(format!("ivanka-verified-r2-{}.fastq", std::process::id()));
    fs::write(
        &a,
        b"@read-a 1:N:0:1\nACGT\n+\n!!!!\n@read-b 1:N:0:1\nACGT\n+\n!!!!\n",
    )
    .unwrap();
    fs::write(
        &b,
        b"@read-a 2:N:0:1\nTGCA\n+\n!!!!\n@read-c 2:N:0:1\nTGCA\n+\n!!!!\n",
    )
    .unwrap();
    let result = Reads::load(a.to_str().unwrap(), b.to_str().unwrap(), None);
    fs::remove_file(a).unwrap();
    fs::remove_file(b).unwrap();
    let err = result
        .err()
        .expect("mismatched original pair must be rejected");
    assert_eq!(err.kind(), ErrorKind::InvalidData);
    assert!(err.to_string().contains("read-pair IDs"));
}
