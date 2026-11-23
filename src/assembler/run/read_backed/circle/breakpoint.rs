use super::support::SPAN;

/// Accept one bounded, independently unsupported junction in a long cycle.
pub(super) fn locate(core: &[u8], mut present: impl FnMut(&[u8]) -> bool) -> Option<usize> {
    if core.len() < 2500 {
        return None;
    }
    // A few supported windows can separate missing observations at one
    // junction because reads cover the same adjacency at different offsets.
    // Widely separated missing regions are not a uniquely localizable cut.
    const MAX_SUPPORTED_BRIDGE: usize = 16;
    let (mut first, mut last, mut missing) = (None, None, 0usize);
    let (mut run, mut multi_runs, mut longest) = (0usize, 0usize, 0usize);
    for (position, window) in core.windows(SPAN).enumerate() {
        if present(window) {
            if run >= 2 {
                multi_runs += 1;
            }
            longest = longest.max(run);
            run = 0;
            continue;
        }
        run += 1;
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
    multi_runs += usize::from(run >= 2);
    longest = longest.max(run);
    if multi_runs != 1 || longest < 3 {
        return None;
    }
    let start = first?;
    let width = last? - start + 1;
    // A missing long window covers SPAN bases, not just its start;
    // a short interval's cut may follow the last missing start.
    let cut = start
        + if width <= 32 {
            SPAN / 2
        } else {
            (width + SPAN) / 2
        };
    if missing < 3 || cut < SPAN || cut > core.len() - SPAN {
        return None;
    }
    Some(cut)
}
