use std::cmp::Ordering;

// Within the high-evidence shortlist prefer total read-backed span.
// For other candidates retain the normalized support-density comparison.
pub(super) fn compare(
    favourite: bool,
    (a_reads, a_len): (usize, usize),
    (b_reads, b_len): (usize, usize),
) -> Ordering {
    let (a, b) = (a_reads as u128, b_reads as u128);
    let (x, y) = (a_len as u128, b_len as u128);
    if favourite {
        (b * y).cmp(&(a * x))
    } else {
        (b * x).cmp(&(a * y))
    }
}
