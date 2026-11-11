use super::dna::{encode, K};
use super::types::{Hit, Reads};
use super::{index, overhang};
use std::collections::HashMap;

mod extend;
mod left;
mod rolling;
