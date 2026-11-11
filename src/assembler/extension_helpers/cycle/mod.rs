mod anchor;
#[cfg(test)]
mod full_scan;
mod repeat;

pub(crate) const CYCLE_MATCH: usize = 512;
pub(super) const CYCLE_MIN_SPACING: usize = 2000;
pub(super) use anchor::next_anchor;
#[cfg(test)]
pub(crate) use full_scan::cycle_end;
pub(super) use repeat::repeats;
