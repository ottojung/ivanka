//! Read-pair depth and mate-locus concordance derived only from original reads.
mod anchors;
mod count;
use super::{index::Hits, Reads, K};
pub(super) use count::{count, Statistics};
