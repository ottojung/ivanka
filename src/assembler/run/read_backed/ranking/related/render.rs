//! Contig interval rendering: localized valleys drop only their unsupported
//! gap; approximate-repeat windows preserve every intervening native base.

use super::{approximate_junction, K};

/// Established rendering: one whole contig, or two flanks around a localized
/// read-unsubstantiated join.
pub(crate) fn pieces(joined: Option<(usize, usize)>, length: usize) -> Vec<(usize, usize)> {
    joined.map_or_else(
        || vec![(0, length)],
        |(a, b)| vec![(0, (a + K).min(length)), (b, length)],
    )
}

/// Similar windows are not a localized unsupported junction. Emit the middle
/// as its own native fragment so no supported base is silently deleted.
pub(crate) fn pieces_keep_middle(windows: (usize, usize), length: usize) -> Vec<(usize, usize)> {
    let a = (windows.0 + K).min(length);
    let b = windows.1.min(length);
    let mut parts = vec![(0, a)];
    if a < b {
        parts.push((a, b));
    }
    if b < length {
        parts.push((b, length));
    }
    parts
}

/// Approximate-repeat rendering, or the whole contig when evidence is absent.
pub(crate) fn approximate_parts(
    seq: &[u8],
    depth: &[u32],
    pairs: &[(usize, usize)],
) -> Vec<(usize, usize)> {
    match approximate_junction(seq, depth, pairs) {
        Some(windows) => pieces_keep_middle(windows, seq.len()),
        None => pieces(None, seq.len()),
    }
}

/// Prefer the localized valley; never drop an intervening supported base.
pub(crate) fn render(
    valley: Option<(usize, usize)>,
    seq: &[u8],
    depth: &[u32],
    pairs: &[(usize, usize)],
) -> Vec<(usize, usize)> {
    if valley.is_some() {
        pieces(valley, seq.len())
    } else {
        approximate_parts(seq, depth, pairs)
    }
}
