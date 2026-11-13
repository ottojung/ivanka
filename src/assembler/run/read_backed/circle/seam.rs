use super::support::SPAN;

/// Every long window crossing the retained core's seam needs read evidence.
pub(super) fn supported(core: &[u8], mut present: impl FnMut(&[u8]) -> bool) -> bool {
    if core.len() < 2 * SPAN {
        return false;
    }
    let flank = SPAN - 1;
    let mut crossing = Vec::with_capacity(2 * flank);
    crossing.extend_from_slice(&core[core.len() - flank..]);
    crossing.extend_from_slice(&core[..flank]);
    crossing.windows(SPAN).all(&mut present)
}
