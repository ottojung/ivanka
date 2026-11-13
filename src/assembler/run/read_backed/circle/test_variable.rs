use super::{overlap, rotate, seam};

#[test]
fn variable_exact_overlap_keeps_existing_31_mer_depth() {
    let mut state = 0x1234_5678u32;
    let core = (0..3400)
        .map(|_| {
            state ^= state << 13;
            state ^= state >> 17;
            state ^= state << 5;
            b"ACGT"[(state & 3) as usize]
        })
        .collect::<Vec<_>>();
    let mut cycle = core.clone();
    cycle.extend_from_slice(&core[..433]);
    assert_ne!(&cycle[..512], &cycle[cycle.len() - 512..]);
    assert_eq!(overlap::length(&cycle, 256, 512), Some(433));
    assert_eq!(overlap::length(&core, 256, 512), None);
    let depth = (0..cycle.len() - 30).map(|i| i as u32).collect::<Vec<_>>();
    let (linear, scores) = rotate::at(&cycle, &depth, 1700, 433, 31).unwrap();
    assert_eq!(linear, [&core[1700..], &core[..1700]].concat());
    assert_eq!(scores.len(), core.len() - 30);
}

#[test]
fn genuine_join_requires_all_original_read_windows() {
    let core = vec![b'A'; 3600];
    let mut windows = 0;
    assert!(seam::supported(&core, |_| {
        windows += 1;
        true
    }));
    assert_eq!(windows, 124);
    let mut windows = 0;
    assert!(!seam::supported(&core, |_| {
        windows += 1;
        windows != 47
    }));
}
