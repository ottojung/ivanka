//! A long terminal overlap plus an isolated unsupported read span signals ambiguity.
pub(crate) fn terminal_overlap(sequence: &[u8]) -> usize {
    let mut prefix = vec![0; sequence.len()];
    for i in 1..sequence.len() {
        let mut j = prefix[i - 1];
        while j > 0 && sequence[i] != sequence[j] {
            j = prefix[j - 1];
        }
        if sequence[i] == sequence[j] {
            j += 1;
        }
        prefix[i] = j;
    }
    prefix.last().copied().unwrap_or(0)
}

pub(crate) fn unsupported_gap(depth: &[u16]) -> Option<(usize, usize)> {
    let covered = depth.iter().filter(|&&count| count >= 2).count();
    if depth.is_empty() || covered * 100 < depth.len() * 98 {
        return None;
    }
    let mut best = None;
    let mut start = None;
    for (i, count) in depth.iter().copied().chain([u16::MAX]).enumerate() {
        if count < 2 && start.is_none() {
            start = Some(i);
        }
        if count >= 2 {
            if let Some(begin) = start.take() {
                if i - begin >= 20 && begin > 101 && i + 101 < depth.len() {
                    if best.is_none_or(|(a, b)| i - begin > b - a) {
                        best = Some((begin, i));
                    }
                }
            }
        }
    }
    best
}
