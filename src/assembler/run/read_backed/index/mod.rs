//! Candidate 31-mer occurrences, retaining both sequence orientations.
mod build;
mod canon;
use super::K;
use std::collections::HashMap;
pub(super) type Key = u64;
pub(super) type Hits = HashMap<Key, Vec<(usize, usize)>>;
pub(super) use build::build;
pub(super) use canon::{pack, rolling};
