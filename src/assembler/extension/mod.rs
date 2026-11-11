pub(super) use super::extension_helpers::record_extension_support;
use super::extension_helpers::{
    choose_extension as choose_with_limit, cycle_cut_keeps_prior_path, summarize, CycleTracker,
};
use super::reads::{encode, rc, Reads, K, MAX_CONTIG_LENGTH, MAX_EXTENSION};
use std::collections::HashSet;
mod grow;
mod probe;
mod trace;
mod update;
pub(super) use grow::extend;
