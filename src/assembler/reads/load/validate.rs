use std::io;

/// Sparse index positions are u16, so rejecting overlength reads is required
/// to prevent silent loss of input evidence.
pub(super) fn indexed_length(read: &[u8]) -> io::Result<()> {
    if read.len() > u16::MAX as usize {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!(
                "FASTQ read length {} exceeds 65535-base index limit",
                read.len()
            ),
        ));
    }
    Ok(())
}
