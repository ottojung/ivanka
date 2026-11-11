use super::Reads;
use std::io;

/// Refuse to report a successful assembly when input reads yielded no path.
/// Explicitly empty inputs retain the zero-pair CLI contract.
pub(super) fn check(reads: &Reads, has_candidate: bool) -> io::Result<()> {
    if has_candidate || reads.seqs.is_empty() {
        return Ok(());
    }
    let strongest = reads.seed_counts.values().copied().max().unwrap_or(0);
    Err(io::Error::new(
        io::ErrorKind::InvalidData,
        format!(
            concat!(
                "no supported contigs from {} pairs ",
                "(strongest sampled 31-mer support={}; ",
                "primary threshold=15); check depth or supply ",
                "same-sample read-derived --seeds"
            ),
            reads.seqs.len() / 4,
            strongest
        ),
    ))
}
