use super::SPAN;

/// Accept one strong internal gap while ignoring a few isolated dropouts.
pub(super) fn locate_strict(core: &[u8], mut present: impl FnMut(&[u8]) -> bool) -> Option<usize> {
    if core.len() < 2500 {
        return None;
    }
    let mut clusters = Vec::<(usize, usize, usize)>::new();
    for (pos, word) in core.windows(SPAN).enumerate() {
        if present(word) {
            continue;
        }
        if let Some((_, end, count)) = clusters.last_mut() {
            if pos <= *end + 17 {
                *end = pos;
                *count += 1;
                continue;
            }
        }
        clusters.push((pos, pos, 1));
    }
    let mut strong = None;
    let mut other_missing = 0usize;
    for cluster in clusters {
        if cluster.2 >= SPAN / 2 {
            if strong.replace(cluster).is_some() {
                return None;
            }
        } else {
            other_missing += cluster.2;
        }
    }
    if other_missing > 3 {
        return None;
    }
    let (start, end, _) = strong?;
    let width = end - start + 1;
    if width > 2 * SPAN {
        return None;
    }
    let cut = start
        + if width <= 32 {
            SPAN / 2
        } else {
            (width + SPAN) / 2
        };
    (cut * 5 >= core.len() && (core.len() - cut) * 5 >= core.len()).then_some(cut)
}
