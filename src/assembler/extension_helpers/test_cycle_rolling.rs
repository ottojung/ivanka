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

#[test] fn exact_cycle_diversity_boundary_seven_vs_eight() {
    use super::cycle::{repeats,CYCLE_MATCH,CYCLE_MIN_SPACING};
    for distinct in [7,8] {
        let mut tract=vec![b'A';CYCLE_MATCH];
        for i in 0..16 {
            let v=i%distinct;
            tract[i*32]=b"ACGT"[v%4];tract[i*32+1]=b"ACGT"[v/4];
        }
        let mut seq=tract.clone();seq.extend(vec![b'G';CYCLE_MIN_SPACING]);
        let second=seq.len();seq.extend_from_slice(&tract);
        assert_eq!(repeats(&seq,0,second,31,encode),distinct==8);
    }
}
