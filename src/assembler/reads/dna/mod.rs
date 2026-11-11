pub(crate) const K: usize = 31;
pub(crate) const INDEX_STEP: usize = 12;
pub(crate) const MAX_EXTENSION: usize = 100;
pub(crate) const MAX_CONTIG_LENGTH: usize = 25000;

mod canonical;
mod encoding;
mod strand;
#[cfg(test)]
mod tests;
pub(crate) use canonical::rolling_canonical_kmers;
pub(crate) use encoding::{decode, encode};
pub(crate) use strand::rc;
