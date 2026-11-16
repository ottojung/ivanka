use super::{Hits, PairLinks, Statistics, K};
mod link;
mod novelty;
mod redundant;
use link::mate_linked;
mod select;
#[cfg(test)]
pub(crate) use select::complement;
pub(crate) use select::complements;

#[cfg(test)]
mod test_link;

#[cfg(test)]
mod test_redundant;

#[cfg(test)]
mod test_selection;

#[cfg(test)]
mod selection_fixture;
