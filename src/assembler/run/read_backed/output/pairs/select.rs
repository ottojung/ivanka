use super::{emit, merge, Entry};

/// Keep only highly repeated complete original read-pair fragments.
pub(super) fn choose(seqs: &[Vec<u8>], existing: &[Entry]) -> Vec<Entry> {
    let (counts, pairs) = merge::count(seqs);
    let mut repeated = counts
        .into_iter()
        .filter(|(_, count)| *count >= 10 && count.saturating_mul(100) >= pairs)
        .collect::<Vec<_>>();
    repeated.sort_unstable_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
    if repeated.len() < 3 || repeated.iter().map(|r| r.1).sum::<usize>() * 4 < pairs {
        return Vec::new();
    }
    emit::output(repeated, existing)
}
