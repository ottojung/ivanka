use super::{read_backed, write_fasta, Reads};
use std::io;

/// The unconfigured MiCall invocation uses the entire read-backed pipeline.
/// Optional research CLI inputs retain the native multi-contig FASTA path.
pub(super) fn write(
    out: &str,
    contigs: &[Vec<u8>],
    reads: &Reads,
    standard: bool,
) -> io::Result<usize> {
    if standard {
        read_backed::write(out, contigs, reads)
    } else {
        write_fasta(out, contigs)?;
        Ok(contigs.len())
    }
}
