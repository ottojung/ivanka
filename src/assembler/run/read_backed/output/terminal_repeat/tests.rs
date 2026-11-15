use super::split;

/// Deterministic non-biological test fixture; no reference templates.
fn dna(length: usize, seed: u64) -> Vec<u8> {
    let mut state = seed;
    (0..length)
        .map(|_| {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            b"ACGT"[(state as usize) & 3]
        })
        .collect()
}

#[test]
fn distant_terminal_reentry_preserves_two_unjoined_original_subpaths() {
    let left = dna(3100, 0x24ef);
    let right = dna(5100, 0x52fa);
    let original = [left.as_slice(), right.as_slice(), &right[..434]].concat();
    let parts = split(2, &original, 151).expect("terminal reentry");
    assert_eq!(parts.len(), 2);
    assert_eq!(parts[0].0, ">ivanka_3_repeat_left");
    assert_eq!(parts[1].0, ">ivanka_3_repeat_right");
    assert_eq!(parts[0].1.as_slice(), &original[..parts[0].1.len()]);
    assert!(original.windows(parts[1].1.len()).any(|s| s == parts[1].1));
    assert!(parts[1].1.len() >= 5100);
}

#[test]
fn ordinary_linear_path_is_preserved() {
    assert!(split(0, &dna(9500, 0x26bb), 151).is_none());
}

#[test]
fn short_repeat_does_not_hide_supported_junctions() {
    let linear = dna(9000, 0x32b3);
    let extended = [linear.as_slice(), &linear[3000..3180]].concat();
    assert!(split(0, &extended, 151).is_none());
}

#[test]
fn repeated_terminal_anchor_is_ambiguous_and_does_not_choose_a_copy() {
    let mut seq = dna(8500, 0x9aba);
    let motif = dna(450, 0x7171);
    seq[3000..3450].copy_from_slice(&motif);
    seq[6000..6450].copy_from_slice(&motif);
    seq.extend_from_slice(&motif);
    assert!(split(0, &seq, 151).is_none());
}

#[test]
fn very_short_or_empty_contigs_stay_unchanged() {
    for length in [0, 1, 255, 1024] {
        assert!(split(0, &dna(length, 0x975), 151).is_none());
    }
}
