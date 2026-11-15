use super::{merge, Entry};

/// Only heavily replicated *complete* original fragments pass this threshold.
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
    let mut result = Vec::new();
    for (sequence, support) in repeated {
        if existing.len() + result.len() >= 16 {
            break;
        }
        let reverse = crate::assembler::reads::rc(&sequence);
        if existing.iter().chain(&result).any(|(_, old): &Entry| {
            old.windows(sequence.len())
                .any(|w| w == sequence || w == reverse)
        }) {
            continue;
        }
        result.push((
            format!(
                ">ivanka_original_pair_{} count={} len={}",
                result.len() + 1,
                support,
                sequence.len()
            ),
            sequence,
        ));
    }
    result
}
