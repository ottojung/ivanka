mod edges;
mod nodes;
mod paths;
#[cfg(test)]
mod tests;
mod walk;

pub(super) type Node = (usize, Vec<u8>);

pub(super) fn chains(fragments: &[(Vec<u8>, usize)]) -> (Vec<(Vec<u8>, usize)>, Vec<usize>) {
    let oriented = nodes::orient(fragments);
    let transitions = edges::build(&oriented);
    paths::collect(&oriented, &transitions, fragments)
}
