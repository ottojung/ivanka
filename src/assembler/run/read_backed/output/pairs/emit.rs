use super::{graph, Entry};

pub(super) fn output(repeated: Vec<(Vec<u8>, usize)>, existing: &[Entry]) -> Vec<Entry> {
    let length = repeated.len().min(32);
    let (paths, used) = graph::chains(&repeated[..length]);
    let candidates = paths
        .into_iter()
        .map(|(seq, count)| (seq, count, true))
        .chain(
            repeated
                .into_iter()
                .enumerate()
                .filter(|(i, _)| !used.contains(i))
                .map(|(_, (seq, count))| (seq, count, false)),
        );
    let mut result = Vec::<Entry>::new();
    for (sequence, support, stitched) in candidates {
        if existing.len() + result.len() >= 16 {
            break;
        }
        let reverse = crate::assembler::reads::rc(&sequence);
        if existing.iter().chain(&result).any(|(_, old)| {
            old.windows(sequence.len())
                .any(|w| w == sequence || w == reverse)
        }) {
            continue;
        }
        let kind = if stitched {
            "overlap_path"
        } else {
            "original_pair"
        };
        result.push((
            format!(
                ">ivanka_{}_{} support_sum={} len={}",
                kind,
                result.len() + 1,
                support,
                sequence.len()
            ),
            sequence,
        ));
    }
    result
}
