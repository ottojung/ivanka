//! Scoring is driven here by original paired records, not fabricated
//! Statistics, so the reference-blind 31-mer scan is exercised end to end.

mod duplicates;
mod loci;
mod scan_equivalence;
mod support;

#[cfg(test)]
pub(super) use super::count;
#[cfg(test)]
pub(super) use super::index;
#[cfg(test)]
pub(super) use super::ranking;
#[cfg(test)]
pub(super) use super::scan;
#[cfg(test)]
pub(super) use super::{Hits, Reads, K};
