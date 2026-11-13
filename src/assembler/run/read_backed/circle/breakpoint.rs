use super::support::SPAN;

/// Accept one bounded, independently unsupported junction in a long cycle.
pub(super) fn locate(core: &[u8], mut present: impl FnMut(&[u8]) -> bool) -> Option<usize> {
    if core.len() < 2500 {
        return None;
    }
    let (mut first, mut last, mut count) = (None, None, 0usize);
    for (position, window) in core.windows(SPAN).enumerate() {
        if present(window) {
            continue;
        }
        if last.is_some_and(|previous| position != previous + 1) {
            return None;
        }
        first.get_or_insert(position);
        last = Some(position);
        count += 1;
        if count > 2 * SPAN {
            return None;
        }
    }
    let cut = first? + if count <= 32 {
        SPAN / 2
    } else {
        (count + SPAN) / 2
    };
    if count < 3 || cut < SPAN || cut > core.len() - SPAN {
        return None;
    }
    Some(cut)
}
