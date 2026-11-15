//! A distant terminal re-entry leaves the long-range path phase ambiguous.
use super::Entry;

/// Emit only original subpaths when a long terminal repeat re-enters the path.
pub(super) fn split(chosen: usize, seq: &[u8], read_len: usize) -> Option<Vec<Entry>> {
    let minimum = read_len.saturating_mul(2).max(256);
    let end = seq.len();
    if end < minimum.saturating_mul(4) {
        return None;
    }
    let tail = &seq[end - minimum..];
    let mut starts = (minimum..end - 2 * minimum).filter(|&i| &seq[i..i + minimum] == tail);
    let (mut early, mut late) = (starts.next()?, end - minimum);
    if starts.next().is_some() {
        return None;
    }
    while early > 0 && late > 0 && seq[early - 1] == seq[late - 1] {
        early -= 1;
        late -= 1;
    }
    let overlap = end - late;
    if early < minimum || early + overlap >= late || late - early < 2 * minimum {
        return None;
    }
    eprintln!(
        "IVANKA_READ_BACKED_TERMINAL_REENTRY first={} last={} overlap={}",
        early, late, overlap
    );
    Some(vec![
        (
            format!(">ivanka_{}_repeat_left", chosen + 1),
            seq[..early + overlap].to_vec(),
        ),
        (
            format!(">ivanka_{}_repeat_right", chosen + 1),
            seq[early..late].to_vec(),
        ),
    ])
}
