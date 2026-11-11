use super::*;

#[test]
fn internal_seed_overhang_can_extend() {
    let seed = b"ACGTACGTACGTACGTACGTACGTACGTACG";
    let mut read = vec![b'G'; 40];
    read.extend_from_slice(seed);
    read.extend_from_slice(b"TTAACCGG");
    let mut index = HashMap::new();
    index.insert(encode(seed).unwrap(), vec![Hit { read: 0, pos: 40 }]);
    let max_read_len = read.len();
    let reads = Reads {
        seqs: vec![read],
        index,
        seed_counts: HashMap::new(),
        max_read_len,
        overhang_cache: Default::default(),
        overlength_rejections: Default::default(),
    };
    let ov = reads.overhangs_with_ids(seed).0;
    assert_eq!(ov, vec![b"TTAACCGG".to_vec()]);
}
