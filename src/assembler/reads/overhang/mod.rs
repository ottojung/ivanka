use super::dna::{K,encode};
use super::types::Reads;
mod scan;
mod cache;
#[cfg(test)] pub(super) use scan::rolling_query;
#[cfg(test)] pub(super) use super::index::build_index;
