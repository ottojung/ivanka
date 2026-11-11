use super::*;

#[test]
fn drops_short_nearly_contained_path_but_keeps_novel_locus() {
    let mut rng = 0x1234_5678_1234_5678u64;
    let long = (0..900)
        .map(|_| {
            rng ^= rng << 13;
            rng ^= rng >> 7;
            rng ^= rng << 17;
            b"ACGT"[(rng & 3) as usize]
        })
        .collect::<Vec<u8>>();
    let mut shorter = long[100..700].to_vec();
    shorter[300] = if shorter[300] == b'A' { b'C' } else { b'A' };
    let novel = vec![b'T'; 400];
    let result = select_supported_contigs(
        vec![long.clone(), shorter, novel.clone()],
        vec![240, 90, 60],
        1000,
        0,
    );
    assert_eq!(result, vec![long, novel]);
}
#[test]
fn supported_full_length_path_survives_dense_short_fragments() {
    let mut seqs = (0..40usize)
        .map(|i| {
            let mut seq = vec![b'A'; K];
            for j in 0..5 {
                seq[j * 6] = b"ACGT"[(i >> (j * 2)) & 3];
            }
            seq
        })
        .collect::<Vec<_>>();
    seqs.push(vec![b'G'; 900]);
    let mut support = vec![100usize; 40];
    support.push(80);
    let retained = select_supported_contigs(seqs, support, 16, 0);
    assert!(retained.len() <= 16);
    assert!(retained.iter().any(|seq| seq.len() == 900));
}
