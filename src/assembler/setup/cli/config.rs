/// Validated command-line settings. Each field has one explicit meaning,
/// avoiding positional mistakes when the invocation contract changes.
pub(crate) struct Config {
    pub(crate) reads1: String,
    pub(crate) reads2: String,
    pub(crate) output: String,
    pub(crate) max_contigs: usize,
    pub(crate) max_pairs: Option<usize>,
    pub(crate) seeds: Option<String>,
    pub(crate) audit: Option<String>,
}
