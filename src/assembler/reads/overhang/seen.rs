// Reuse storage across extension probes without clearing every read bit.
#[derive(Default)]
pub(crate) struct Seen {
    pub(super) words: Vec<u64>,
    pub(super) touched: Vec<usize>,
}
impl Seen {
    pub(super) fn contains(&self, id: usize) -> bool {
        self.words.get(id / 64).is_some_and(|w|w & (1u64 << (id % 64)) != 0)
    }
    pub(super) fn mark(&mut self, id: usize) {
        let word = id / 64;
        if word >= self.words.len() { self.words.resize(word + 1, 0); }
        if self.words[word] == 0 { self.touched.push(word); }
        self.words[word] |= 1u64 << (id % 64);
    }
    pub(super) fn clear(&mut self) {
        for word in self.touched.drain(..) { self.words[word] = 0; }
    }
}
