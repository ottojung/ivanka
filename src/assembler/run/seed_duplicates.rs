//! Optional MiCall adapter contract: already-emitted G2P seeds are not
//! emitted again by the assembler. No external references are consulted.
use super::{fasta_seeds, rc};
use std::collections::HashSet;
use std::io;

fn canonical(seq: &[u8]) -> Vec<u8> {
    let reverse = rc(seq);
    if seq < reverse.as_slice() {
        seq.to_vec()
    } else {
        reverse
    }
}

/// Retain only native paths not already carried by caller-supplied seeds.
pub(super) fn keep_indices(contigs: &[Vec<u8>], path: &str) -> io::Result<Vec<usize>> {
    let supplied = fasta_seeds(path)?
        .into_iter()
        .map(|seq| canonical(&seq))
        .collect::<HashSet<_>>();
    let kept = contigs
        .iter()
        .enumerate()
        .filter_map(|(index, seq)| (!supplied.contains(&canonical(seq))).then_some(index))
        .collect::<Vec<_>>();
    eprintln!(
        "IVANKA_NATIVE_SUPPLIED_SEED_DUPLICATES removed={} remaining={}",
        contigs.len() - kept.len(),
        kept.len()
    );
    Ok(kept)
}

#[cfg(test)]
mod tests;
#[cfg(test)]
mod tests_tails;
