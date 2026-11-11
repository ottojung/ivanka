use std::collections::{HashMap, HashSet};
mod evidence;

mod observation;
pub(super) use observation::Observation;

pub(super) fn local_variants(
    rejected: &[(Vec<u8>, usize)],
    output: &[Vec<u8>],
    sampled: &HashMap<u64, u32>,
    canonical: fn(&[u8]) -> Option<u64>,
) -> Vec<Observation> {
    let represented = output
        .iter()
        .flat_map(|s| s.windows(31).filter_map(canonical))
        .collect::<HashSet<_>>();
    let mut result = Vec::new();
    let mut observed = HashSet::new();
    for (seq, &support) in rejected.iter().map(|(s, n)| (s, n)) {
        if result.len() >= 16 {
            break;
        }
        for (index, parent) in output.iter().enumerate() {
            let Some((pos, novel_witnesses, context)) =
                evidence::evidence(seq, parent, &represented, sampled, canonical)
            else {
                continue;
            };
            if !observed.insert((index, pos, seq[pos])) {
                break;
            }
            result.push(Observation {
                parent: index + 1,
                pos,
                original: parent[pos],
                alternate: seq[pos],
                length: seq.len(),
                support,
                kmer_witnesses: novel_witnesses,
                context,
            });
            break;
        }
    }
    result
}
