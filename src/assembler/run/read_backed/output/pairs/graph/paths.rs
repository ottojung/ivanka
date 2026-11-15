use super::{walk, Node};
use std::collections::{HashMap, HashSet};

pub(super) fn collect(
    nodes: &[Node],
    edges: &HashMap<usize, (usize, usize)>,
    fragments: &[(Vec<u8>, usize)],
) -> (Vec<(Vec<u8>, usize)>, Vec<usize>) {
    let destinations = edges.values().map(|&(id, _)| id).collect::<HashSet<_>>();
    let mut used = HashSet::<usize>::new();
    let mut result = Vec::new();
    for root in 0..nodes.len() {
        if destinations.contains(&root)
            || !edges.contains_key(&root)
            || used.contains(&nodes[root].0)
        {
            continue;
        }
        if let Some((sequence, ids)) = walk::path(nodes, edges, root, &used) {
            let support = ids.iter().map(|&i| fragments[i].1).sum();
            result.push((sequence, support));
            used.extend(ids);
        }
    }
    result.sort_unstable_by(|a, b| b.0.len().cmp(&a.0.len()).then_with(|| a.0.cmp(&b.0)));
    (result, used.into_iter().collect())
}
