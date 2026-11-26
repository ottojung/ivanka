mod band;
mod calls;
#[cfg(test)]
mod controls;
#[cfg(test)]
mod equivalence;
#[cfg(test)]
mod legacy;
#[cfg(test)]
mod legacy_final;
mod merge;
mod pairscan;
mod record;

pub(super) use super::evidence::{validw, FlankIndex, Prep, A, INV, K128};
pub(super) use pairscan::unsupported_pair;

// One flank index per candidate; reads are located against it once and the
// resulting position-sorted calls feed the banded variant-pair scan.
pub(super) fn observations(seq: &[u8], reads: &[Vec<u8>], preps: &[Prep]) -> Vec<Vec<(usize, u8)>> {
    let index = super::evidence::uniq_flanks(seq);
    reads
        .chunks_exact(4)
        .zip(preps.chunks_exact(4))
        .map(|(pr, pp)| {
            merge::pair_calls(
                [&pr[0], &pr[1], &pr[2], &pr[3]],
                [&pp[0], &pp[1], &pp[2], &pp[3]],
                &index,
            )
        })
        .collect()
}
