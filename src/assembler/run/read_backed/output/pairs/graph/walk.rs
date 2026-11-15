use super::Node;
use std::collections::{HashMap, HashSet};

/// An overlap path never reuses a fragment or adds unobserved bases.
pub(super) fn path(
    nodes: &[Node],
    edges: &HashMap<usize, (usize, usize)>,
    start: usize,
    globally_used: &HashSet<usize>,
) -> Option<(Vec<u8>, Vec<usize>)> {
    let mut visited = HashSet::from([nodes[start].0]);
    let mut ids = vec![nodes[start].0];
    let mut sequence = nodes[start].1.clone();
    let mut current = start;
    while let Some(&(next, overlap)) = edges.get(&current) {
        let (id, fragment) = &nodes[next];
        if visited.contains(id)
            || globally_used.contains(id)
            || sequence.len() + fragment.len() - overlap > 25000
        {
            break;
        }
        sequence.extend_from_slice(&fragment[overlap..]);
        visited.insert(*id);
        ids.push(*id);
        current = next;
    }
    (ids.len() >= 2).then_some((sequence, ids))
}
