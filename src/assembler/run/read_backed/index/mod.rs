//! Candidate 31-mer occurrences, retaining both sequence orientations.
mod build;
use super::K;
use std::collections::HashMap;
pub(super) type Key = [u8; K];
pub(super) type Hits = HashMap<Key, Vec<(usize, usize)>>;
pub(super) use build::build;
