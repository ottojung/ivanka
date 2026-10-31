use super::cycle::next_anchor;
use super::test_cycle::encode;

#[test] fn rolling_anchors_match_full_encoding_including_ambiguous_bases() {
    let mut x = 0x45f1bc79e372d451_u64;
    let mut seq = Vec::new();
    for i in 0..10000 {
        x ^= x << 13; x ^= x >> 7; x ^= x << 17;
        seq.push(if i % 113 == 0 { b'N' } else { b"ACGT"[(x % 4) as usize] });
    }
    let mut prev = None;
    for i in 0..=seq.len()-512 {
        let rolling = next_anchor(&seq, i, 31, prev, encode);
        assert_eq!(rolling, encode(&seq[i..i+31]), "window {i}");
        prev = rolling;
    }
}
