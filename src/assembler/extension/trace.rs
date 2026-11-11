use super::summarize;
pub(super) fn stalled(seq: &[u8], right_reads: &[Vec<u8>], left_reads: &[Vec<u8>]) {
    if std::env::var_os("IVANKA_TRACE_EXTENSIONS").is_some() {
        eprintln!(
            concat!(
                "EXTENSION_STOP length={} right_reads={} right_bases={:?} ",
                "left_reads={} left_bases={:?}"
            ),
            seq.len(),
            right_reads.len(),
            summarize(right_reads),
            left_reads.len(),
            summarize(left_reads)
        );
    }
}
