//! Minimal truth-free counterexample for read-supported traversal uniqueness.
//!
//! A duplicated path accumulated by substitution is not an exact repeat. The
//! existing cycle protection matches exact 31-mers, so it cannot recognise
//! this shape. This fixture states the gap; it does not change assembly.

use super::{cycle_end, encode};

fn deterministic_path(seed: u64, length: usize) -> Vec<u8> {
    let mut state = seed;
    (0..length)
        .map(|_| {
            state = state.wrapping_mul(6364136223846793005).wrapping_add(1);
            [b'A', b'C', b'G', b'T'][((state >> 33) & 3) as usize]
        })
        .collect()
}

/// Substitute one base in every 12; every 31-base window then carries at
/// least two substitutions, so no exact 31-mer survives between the copies.
fn diverged(path: &[u8]) -> Vec<u8> {
    let mut copy = path.to_vec();
    for index in (0..copy.len()).step_by(12) {
        copy[index] = match copy[index] {
            b'A' => b'C',
            b'C' => b'G',
            b'G' => b'T',
            _ => b'A',
        };
    }
    copy
}

fn joined(first: &[u8], flank: &[u8], tail: &[u8]) -> Vec<u8> {
    let mut out = first.to_vec();
    out.extend_from_slice(flank);
    out.extend_from_slice(tail);
    out
}

#[test]
fn exact_duplicate_is_cut_but_diverged_duplicate_is_not() {
    let first = deterministic_path(0x1234_5678_9abc_def0, 4000);
    let flank = deterministic_path(0xfeed_face_cafe_babe, 1000);
    let third = deterministic_path(0xdead_beef_1234_5678, 4000);
    let second = diverged(&first);
    assert!(
        cycle_end(&joined(&first, &flank, &first), 31, encode).is_some(),
        "an exact duplicated path must be recognised as a cycle"
    );
    assert!(
        cycle_end(&joined(&first, &flank, &second), 31, encode).is_none(),
        "a diverged duplicated path escapes exact 31-mer cycle protection"
    );
    assert!(
        cycle_end(&joined(&first, &flank, &third), 31, encode).is_none(),
        "biologically distinct paths must not be cut"
    );
}
