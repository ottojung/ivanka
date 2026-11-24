use super::{fasta_seeds, rolling_canonical_kmers, Reads};
use std::collections::{HashMap, HashSet};
use std::io;

/// Minimum number of distinct observed pairs supporting a retained fragment.
pub(super) const MIN_SUPPORT: usize = 15;

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

/// Rank reads by the number of distinct observed pairs they appear in.
/// Identical pair sequences are counted once; no molecule identity is assumed.
pub(super) fn ranked(reads: &Reads) -> Vec<(Vec<u8>, usize)> {
    let mut support = HashMap::<Vec<u8>, usize>::new();
    let mut pairs = HashSet::<(Vec<u8>, Vec<u8>)>::new();
    for observed in reads.seqs.chunks_exact(4).take(80_000) {
        if !pairs.insert((observed[0].clone(), observed[2].clone())) {
            continue;
        }
        *support.entry(observed[0].clone()).or_insert(0) += 1;
        *support.entry(observed[2].clone()).or_insert(0) += 1;
    }
    let mut candidates = support
        .into_iter()
        .filter(|&(_, n)| n >= MIN_SUPPORT)
        .collect::<Vec<_>>();
    candidates.sort_by(|a, b| {
        b.1.cmp(&a.1)
            .then_with(|| b.0.len().cmp(&a.0.len()))
            .then_with(|| a.0.cmp(&b.0))
    });
    candidates
}

pub(super) fn cover(represented: &mut HashSet<u64>, seq: &[u8]) {
    for k in rolling_canonical_kmers(seq) {
        represented.insert(k);
    }
}

pub(super) fn uncovered(represented: &HashSet<u64>, seq: &[u8]) -> bool {
    !rolling_canonical_kmers(seq).any(|k| represented.contains(&k))
}
