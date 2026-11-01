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

#[test] fn overlength_fallback_finds_cycle_masked_by_near_match() {
    use super::cycle::{cycle_end,CYCLE_MATCH};
    use super::cycle_state::context_cycle_end;
    use super::test_cycle::encode;
    let mut state=0x9e3779b97f4a7c15u64;
    let mut random=|n| (0..n).map(|_|{
        state^=state<<13;state^=state>>7;state^=state<<17;
        b"ACGT"[(state&3) as usize]
    }).collect::<Vec<u8>>();
    let tract=random(CYCLE_MATCH);
    let mut near=tract.clone();
    near[CYCLE_MATCH-1]=if near[CYCLE_MATCH-1]==b'A' {b'C'} else {b'A'};
    let mut seq=near;
    seq.extend(random(2200-CYCLE_MATCH));
    seq.extend(&tract);
    seq.extend(random(2200-CYCLE_MATCH));
    seq.extend(&tract);
    assert_eq!(cycle_end(&seq,31,encode),None);
    assert_eq!(context_cycle_end(&seq,31,encode),Some(seq.len()));
}
#[test] fn low_complexity_overlength_is_not_a_supported_cycle() {
    use super::cycle_state::context_cycle_end;
    use super::test_cycle::encode;
    assert_eq!(context_cycle_end(&vec![b'A';25050],31,encode),None);
}
