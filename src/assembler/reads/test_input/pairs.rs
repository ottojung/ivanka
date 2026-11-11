#[test]
fn paired_reads_keep_original_and_reverse_complement_order() {
    use super::types::Reads;
    let dir = std::env::temp_dir();
    let a = dir.join(format!("ivanka-move-r1-{}.fastq", std::process::id()));
    let b = dir.join(format!("ivanka-move-r2-{}.fastq", std::process::id()));
    std::fs::write(&a, b"@paired\nAAGT\n+\n!!!!\n").unwrap();
    std::fs::write(&b, b"@paired\nTTGC\n+\n!!!!\n").unwrap();
    let reads = Reads::load(a.to_str().unwrap(), b.to_str().unwrap(), None).unwrap();
    std::fs::remove_file(a).unwrap();
    std::fs::remove_file(b).unwrap();
    assert_eq!(
        reads.seqs,
        vec![
            b"AAGT".to_vec(),
            b"ACTT".to_vec(),
            b"TTGC".to_vec(),
            b"GCAA".to_vec()
        ]
    );
}
