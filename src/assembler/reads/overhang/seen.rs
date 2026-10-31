// A byte per original read, reused across exact-overlap queries.
#[derive(Default)]
pub(crate) struct Seen { marks: Vec<u8>, generation: u8 }

impl Seen {
    pub(super) fn begin(&mut self, reads: usize) {
        if self.marks.len() < reads { self.marks.resize(reads, 0); }
        self.generation = self.generation.wrapping_add(1);
        if self.generation == 0 {
            self.marks.fill(0);
            self.generation = 1;
        }
    }
    pub(super) fn contains(&self, id: usize) -> bool {
        self.marks[id] == self.generation
    }
    pub(super) fn insert(&mut self, id: usize) {
        self.marks[id] = self.generation;
    }
}

#[test]
fn generations_do_not_leak_between_queries_or_wrap() {
    let mut seen = Seen::default();
    for i in 0..520 {
        seen.begin(3);
        assert!(!seen.contains(0), "query {i}");
        assert!(!seen.contains(1), "query {i}");
        seen.insert(i % 2);
        assert!(seen.contains(i % 2));
        assert!(!seen.contains(2));
    }
}
