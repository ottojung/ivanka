mod dna;
mod fastq;
mod index;
mod input;
mod load;
mod overhang;
mod types;
pub(super) use dna::{
    decode, encode, rc, rolling_canonical_kmers, K, MAX_CONTIG_LENGTH, MAX_EXTENSION,
};
pub(super) use input::fasta_seeds;
pub(super) use types::Reads;
#[cfg(test)]
mod test_input;
#[cfg(test)]
mod test_overhang;
