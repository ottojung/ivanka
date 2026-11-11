use super::{CycleTracker, HashMap};
impl CycleTracker {
    pub(crate) fn new() -> Self {
        Self {
            first: HashMap::new(),
            scanned: 0,
            previous: None,
        }
    }
}
