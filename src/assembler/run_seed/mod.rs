use super::extension::extend;
#[cfg(test)]
use super::ranking::canonical_kmer;
use super::reads::rolling_canonical_kmers;
use super::reads::K;
use super::reads::{decode, Reads};
use super::setup::balanced_seed_candidates;
use std::collections::HashSet;

mod assembly;
pub(super) use assembly::assemble_candidates;
mod rescue;
mod rescue_rank;
pub(super) use rescue::rescue_short;

pub(super) use rescue_rank::append_preserving_diversity;

#[cfg(test)]
mod rescue_rank_equiv_test;
#[cfg(test)]
mod rescue_rank_test;
