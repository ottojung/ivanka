use super::{fasta_seeds, rolling_canonical_kmers};
use std::collections::HashSet;
use std::io;

/// Mark regions already covered by selected contigs or supplied seeds.
pub(super) fn covered(
    represented: &mut HashSet<u64>,
    contigs: &[Vec<u8>],
    supplied: Option<&str>,
) -> io::Result<()> {
    for seq in contigs {
        cover(represented, seq);
    }
    if let Some(path) = supplied {
        for seed in fasta_seeds(path)? {
            cover(represented, &seed);
        }
    }
    Ok(())
}

pub(super) fn cover(represented: &mut HashSet<u64>, seq: &[u8]) {
    for k in rolling_canonical_kmers(seq) {
        represented.insert(k);
    }
}

pub(super) fn uncovered(represented: &HashSet<u64>, seq: &[u8]) -> bool {
    !rolling_canonical_kmers(seq).any(|k| represented.contains(&k))
}
