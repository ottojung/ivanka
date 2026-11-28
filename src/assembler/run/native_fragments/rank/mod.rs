mod fragments;
mod mates;
mod pair_support;

pub(super) use super::{rolling_canonical_kmers, Reads};
pub(crate) use fragments::merge;
pub(crate) use mates::pairs;
pub(crate) use pair_support::{counts, has_kmers};
