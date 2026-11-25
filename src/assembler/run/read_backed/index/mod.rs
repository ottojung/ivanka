//! Candidate 31-mer occurrences, retaining both sequence orientations.
mod build;
use super::K;
use std::collections::HashMap;
pub(super) type Key = [u8; K];
/// Candidate, 31-mer locus and strand relative to the contig (true = forward).
pub(super) type Hits = HashMap<Key, Vec<(usize, usize, bool)>>;
pub(super) use build::build;
