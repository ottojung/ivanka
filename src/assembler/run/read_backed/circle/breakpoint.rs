use super::support::SPAN;

/// Accept one bounded, independently unsupported junction in a long cycle.
pub(super) fn locate(core: &[u8], present: impl FnMut(&[u8]) -> bool) -> Option<usize> {
    locate_with_minimum(core, present, 3)
}

/// Linear paths need stronger evidence before withholding a claimed join.
pub(super) fn locate_strict(core: &[u8], present: impl FnMut(&[u8]) -> bool) -> Option<usize> {
    let cut = locate_with_minimum(core, present, SPAN / 2)?;
    // An unsupported edge is not evidence for discarding a long linear join.
    (cut * 5 >= core.len() && (core.len() - cut) * 5 >= core.len()).then_some(cut)
}

fn locate_with_minimum(
    core: &[u8],
    mut present: impl FnMut(&[u8]) -> bool,
    minimum: usize,
) -> Option<usize> {
    if core.len() < 2500 {
        return None;
    }
    // A few supported windows can separate missing observations at one
    // junction because reads cover the same adjacency at different offsets.
    // Widely separated missing regions are not a uniquely localizable cut.
    const MAX_SUPPORTED_BRIDGE: usize = 16;
    let (mut first, mut last, mut missing) = (None, None, 0usize);
    for (position, window) in core.windows(SPAN).enumerate() {
        if present(window) {
            continue;
        }
        if last.is_some_and(|previous| position > previous + MAX_SUPPORTED_BRIDGE + 1) {
            return None;
        }
        let start = *first.get_or_insert(position);
        last = Some(position);
        missing += 1;
        if position - start + 1 > 2 * SPAN {
            return None;
        }
    }
    let start = first?;
    let width = last? - start + 1;
    let cut = start
        + if width <= 32 {
            SPAN / 2
        } else {
            (width + SPAN) / 2
        };
    if missing < minimum || cut < SPAN || cut > core.len() - SPAN {
        return None;
    }
    Some(cut)
}
