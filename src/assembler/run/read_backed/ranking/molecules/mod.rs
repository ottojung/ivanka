use super::{Hits, Reads, K};
use std::collections::HashMap;
mod anchors;
mod links;
pub(super) use anchors::anchor;
pub(crate) use links::links;
pub(crate) type PairLinks = HashMap<(usize, usize), usize>;
