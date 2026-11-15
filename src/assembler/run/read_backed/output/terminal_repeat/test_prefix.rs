use super::split;

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
fn prefix_repeat_is_recognized_symmetrically() {
    let a = dna(3100, 0x51f7);
    let b = dna(5100, 0xa57b);
    let mut path = [a.as_slice(), b.as_slice(), &b[..434]].concat();
    path.reverse();
    let result = split(0, &path, 151).expect("unbridged prefix repeat");
    assert_eq!(result.len(), 2);
    for (_, fragment) in result {
        assert!(fragment.len() >= 3000);
        assert!(path
            .windows(fragment.len())
            .any(|window| window == fragment));
    }
}

#[test]
fn ordinary_short_or_unrepeated_paths_are_not_cut() {
    for length in [0, 500, 3500, 9600] {
        assert!(split(0, &dna(length, 0xf173), 151).is_none());
    }
}
