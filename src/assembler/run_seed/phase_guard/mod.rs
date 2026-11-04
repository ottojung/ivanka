// Experimental reference-free read-pair phase check. Not a physical-molecule model.
mod index;
mod collect;
mod detect;
mod split;
mod mask;
mod place;
#[cfg(test)] mod tests;
pub(crate) use split::{split_unsupported_contigs,audit_unsupported_contigs};
pub(crate) use mask::mask_unsupported_contigs;
