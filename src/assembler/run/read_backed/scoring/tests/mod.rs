//! Permanent regression tests for the byte-equivalent scoring refactor.
pub(super) use super::{count, index, Accumulator, Hits, Reads, K};
mod accumulator;
mod boundary;
mod byte_index;
mod equivalence;
mod pair_cap;
mod reference;
mod skip;
mod support;
