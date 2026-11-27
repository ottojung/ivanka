//! Compact wrappers for the seven opt-in trace stages.
//! Each stage is derived only from candidates already in memory; no reference
//! or truth input is read here.
use super::emit;
use std::io;

/// FNV-1a digest of a candidate; the sequence itself is only in the private file.
pub(super) fn hash(data: &[u8]) -> String {
    let mut value = 0xcbf29ce484222325u64;
    for &byte in data {
        value = (value ^ u64::from(byte)).wrapping_mul(0x100000001b3);
    }
    format!("{value:016x}")
}

/// Emit a whole candidate set with its read-support counts.
pub(super) fn emit_all(
    out: &str,
    stage: &str,
    contigs: &[Vec<u8>],
    support: &[usize],
) -> io::Result<()> {
    let rows = contigs
        .iter()
        .enumerate()
        .map(|(i, seq)| (i, seq.as_slice(), support.get(i).copied().unwrap_or(0)))
        .collect::<Vec<_>>();
    emit(out, stage, &rows)
}

/// Emit one already-selected candidate by index.
pub(super) fn emit_one(
    out: &str,
    stage: &str,
    contigs: &[Vec<u8>],
    support: &[usize],
    index: usize,
) -> io::Result<()> {
    emit(
        out,
        stage,
        &[(index, contigs[index].as_slice(), support[index])],
    )
}

/// Emit final selected components; they carry no independent support count.
pub(super) fn emit_selected(
    out: &str,
    stage: &str,
    selected: &[(String, Vec<u8>)],
) -> io::Result<()> {
    let rows = selected
        .iter()
        .enumerate()
        .map(|(i, entry)| (i, entry.1.as_slice(), 0))
        .collect::<Vec<_>>();
    emit(out, stage, &rows)
}
