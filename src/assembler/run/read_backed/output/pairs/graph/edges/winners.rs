use super::Edge;
use std::collections::HashMap;

/// An edge is unique only if the next best candidate is much weaker.
pub(super) fn unique(edges: &[Edge], outgoing: bool) -> HashMap<usize, Edge> {
    let mut groups = HashMap::<usize, Vec<Edge>>::new();
    for &edge in edges {
        let node = if outgoing { edge.0 } else { edge.1 };
        groups.entry(node).or_default().push(edge);
    }
    let mut winners = HashMap::new();
    for (node, mut options) in groups {
        options.sort_unstable_by(|a, b| b.2.cmp(&a.2).then_with(|| a.cmp(b)));
        let best = options[0];
        if options.len() == 1 || best.2.saturating_sub(options[1].2) >= 12 {
            winners.insert(node, best);
        }
    }
    winners
}
