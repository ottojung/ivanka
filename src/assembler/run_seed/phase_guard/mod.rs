// Experimental reference-free read-pair phase check. Not a physical-molecule model.
mod index;
mod collect;
mod detect;
mod split;
#[cfg(test)] mod test_support;
#[cfg(test)] mod test_guard;
#[cfg(test)] mod test_unlinked;
#[cfg(test)] mod test_false_positives;
mod place;
pub(crate) use split::split_unsupported_contigs;
