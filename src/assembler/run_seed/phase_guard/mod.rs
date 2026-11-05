// Experimental reference-free read-pair phase check. Not a physical-molecule model.
mod index;
mod collect;
mod detect;
mod split;
mod mask;
mod place;
mod quality_filter;
#[cfg(test)] mod tests;
pub(crate) use apply::apply;
mod apply;
