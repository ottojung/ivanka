use super::{infer, trim, HashMap};

fn read(mut seed: u32, len: usize) -> Vec<u8> {
    (0..len)
        .map(|_| {
            seed ^= seed << 13;
            seed ^= seed >> 17;
            seed ^= seed << 5;
            b"ACGT"[(seed as usize) & 3]
        })
        .collect()
}

fn pairs(suffix: &[u8], diverse: bool) -> Vec<Vec<u8>> {
    let rc = crate::assembler::reads::rc;
    let mut output = Vec::new();
    for i in 1..=150 {
        for mate in 0..2 {
            let mut seq = read(if diverse { i * 7 + mate } else { 7 }, 130);
            seq.extend_from_slice(suffix);
            output.push(seq.clone());
            output.push(rc(&seq));
        }
    }
    output
}

#[test]
fn identifies_shared_highly_diverse_terminal_artifact() {
    let suffix = b"AGATCGGAAGAGCACACG";
    let mut reads = pairs(suffix, true);
    assert_eq!(infer::common(&reads), Some(suffix.to_vec()));
    let mut seeds = HashMap::new();
    assert_eq!(trim(&mut reads, &mut seeds), 300);
    assert!(reads.iter().all(|seq| seq.len() == 130));
    assert!(!seeds.is_empty());
}

#[test]
fn never_clips_a_clonal_library_same_mate_ends() {
    let mut reads = pairs(b"AGATCGGAAGAGCACACG", false);
    let mut seeds = HashMap::new();
    assert_eq!(trim(&mut reads, &mut seeds), 0);
    assert!(reads.iter().all(|seq| seq.len() == 148));
}
