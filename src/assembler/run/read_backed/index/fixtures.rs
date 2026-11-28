//! Deterministic synthetic sequences for diagnostic control tests. These
//! helpers are compiled only under `cfg(test)` and never reach assembly.

pub(super) fn genome(len: usize, seed: u64) -> Vec<u8> {
    let mut state = seed;
    (0..len)
        .map(|_| {
            state = state
                .wrapping_mul(6_364_136_223_846_793_005)
                .wrapping_add(1_442_695_040_888_963_407);
            b"ACGT"[((state >> 33) & 3) as usize]
        })
        .collect()
}

pub(super) fn diverge(source: &[u8], percent: u64, seed: u64) -> Vec<u8> {
    let mut state = seed;
    source
        .iter()
        .map(|&base| {
            state = state
                .wrapping_mul(6_364_136_223_846_793_005)
                .wrapping_add(7);
            if state % 100 < percent {
                b"ACGT"[((state >> 17) & 3) as usize]
            } else {
                base
            }
        })
        .collect()
}
