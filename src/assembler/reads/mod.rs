mod dna;
mod input;
mod types;
mod load;
mod overhang;
pub(super) use dna::{K, MAX_EXTENSION, MAX_CONTIG_LENGTH, encode, decode, rc};
pub(super) use input::fasta_seeds;
pub(super) use types::{Hit, Reads};
