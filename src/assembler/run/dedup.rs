//! Collapse redundant molecule representations before writing the FASTA.
//!
//! Read-derived candidates can resolve to the same double-stranded molecule in
//! more than one direction. Emitting that molecule twice leaves downstream
//! read-count attribution with two indistinguishable rows and silently drops
//! the molecule's support. Keeping the first occurrence is deterministic, uses
//! no reference or score, and preserves every distinct sequence.

/// Remove canonical-duplicate molecules, keeping the first occurrence.
pub(super) fn collapse(contigs: &[Vec<u8>]) -> Vec<Vec<u8>> {
    let mut seen = std::collections::HashSet::new();
    let mut kept = Vec::with_capacity(contigs.len());
    for contig in contigs {
        if seen.insert(canonical_key(contig)) {
            kept.push(contig.clone());
        }
    }
    kept
}

/// Strand-canonical identity: the lesser of a sequence and its reverse
/// complement, matching downstream molecule attribution of read support.
fn canonical_key(sequence: &[u8]) -> Vec<u8> {
    let forward: Vec<u8> = sequence.iter().map(u8::to_ascii_uppercase).collect();
    let reverse: Vec<u8> = forward
        .iter()
        .rev()
        .map(|base| match base {
            b'A' => b'T',
            b'C' => b'G',
            b'G' => b'C',
            b'T' => b'A',
            other => *other,
        })
        .collect();
    if reverse < forward {
        reverse
    } else {
        forward
    }
}

#[cfg(test)]
mod tests;
