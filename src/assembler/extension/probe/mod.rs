mod refs;
use super::{choose_with_limit, rc, Reads, MAX_EXTENSION};
use std::rc::Rc;

// Read overhang observations are scoped to the exact contig ends being probed.
type Cached = Rc<(Vec<Vec<u8>>, Vec<u32>)>;
pub(super) struct Probe {
    right_cached: Option<Cached>,
    left_cached: Option<Cached>,
    pub(super) right: Vec<u8>,
    pub(super) left: Vec<u8>,
    pub(super) left_rc: Vec<u8>,
}

/// Probe both contig ends using the same read evidence and extension limits.
/// Owning the cached overhangs keeps every returned read slice valid throughout
/// the later extension decision, even when the cache itself is cleared.
pub(super) fn scan(
    seq: &[u8],
    reads: &Reads,
    right_stalled: bool,
    left_stalled: bool,
    min_cov: usize,
    min_ratio: usize,
) -> Probe {
    let empty = (Vec::new(), Vec::new());
    let right_cached = if right_stalled {
        None
    } else {
        Some(reads.cached_overhangs(&seq))
    };
    let (right_reads, _) = right_cached.as_deref().unwrap_or(&empty);
    let right = choose_with_limit(&right_reads, min_cov, min_ratio, MAX_EXTENSION);
    let left_cached = if left_stalled {
        None
    } else {
        Some(reads.cached_overhangs(&rc(&seq[..seq.len().min(reads.max_read_len)])))
    };
    let (left_reads, _) = left_cached.as_deref().unwrap_or(&empty);
    let left_rc = choose_with_limit(&left_reads, min_cov, min_ratio, MAX_EXTENSION);
    let left = rc(&left_rc);
    Probe {
        right_cached,
        left_cached,
        right,
        left,
        left_rc,
    }
}
