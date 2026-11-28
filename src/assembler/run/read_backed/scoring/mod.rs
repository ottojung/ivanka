mod count;
mod evidence;
mod scan;
mod spans;
mod statistics;
#[cfg(test)]
mod tests;
pub(super) use super::{index::Hits, Reads, K};
pub(super) use count::count;
pub(super) use statistics::Statistics;
pub(super) use std::collections::{HashMap, HashSet};
