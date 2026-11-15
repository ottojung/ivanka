use super::Node;

pub(super) fn orient(fragments: &[(Vec<u8>, usize)]) -> Vec<Node> {
    let mut nodes = Vec::with_capacity(fragments.len() * 2);
    for (id, (sequence, _)) in fragments.iter().enumerate() {
        nodes.push((id, sequence.clone()));
        nodes.push((id, crate::assembler::reads::rc(sequence)));
    }
    nodes
}
