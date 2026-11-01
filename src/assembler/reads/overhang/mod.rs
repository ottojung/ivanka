use super::dna::{K,encode};
use super::types::Reads;
mod scan;
mod cache;
#[cfg(test)] pub(super) use scan::rolling_query;
#[cfg(test)] pub(super) use super::index::build_index;
#[cfg(test)] pub(super) use super::dna::rc;
#[cfg(test)] mod test_left_rc;

#[cfg(test)] mod test_used;
#[cfg(test)] pub(super) use super::types::Hit;

#[cfg(test)] mod test_long_read;
