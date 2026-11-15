use super::{winners::unique, Edge, Node};
use std::collections::HashMap;

fn overlap(left: &[u8], right: &[u8]) -> usize {
    let span = left.len().min(right.len()).saturating_sub(1);
    (42..=span)
        .rev()
        .find(|&k| left[left.len() - k..] == right[..k])
        .unwrap_or(0)
}

/// Preserve only mutually best, uniquely supported suffix-prefix adjacencies.
pub(crate) fn build(nodes: &[Node]) -> HashMap<usize, (usize, usize)> {
    let mut edges = Vec::<Edge>::new();
    for (i, (a, left)) in nodes.iter().enumerate() {
        for (j, (b, right)) in nodes.iter().enumerate() {
            if a == b {
                continue;
            }
            let k = overlap(left, right);
            if k >= 42 {
                edges.push((i, j, k));
            }
        }
    }
    let successors = unique(&edges, true);
    let predecessors = unique(&edges, false);
    successors
        .into_iter()
        .filter_map(|(src, (a, dst, k))| {
            (predecessors.get(&dst) == Some(&(a, dst, k))).then_some((src, (dst, k)))
        })
        .collect()
}
