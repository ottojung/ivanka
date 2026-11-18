#[cfg(test)]
use super::build_index;
use super::Reads;
use std::rc::Rc;
impl Reads {
    // Any extending read overlaps fewer than max_read_len bases, so all
    // successful anchors depend only on this exact suffix (or the whole
    // sequence when shorter); their traversal order is also unchanged.
    pub(crate) fn cached_overhangs(&self, contig: &[u8]) -> Rc<(Vec<Vec<u8>>, Vec<u32>)> {
        let key = &contig[contig.len().saturating_sub(self.max_read_len)..];
        if let Some(v) = self.overhang_cache.borrow().get(key) {
            return Rc::clone(v);
        }
        let value = Rc::new(self.overhangs_with_ids(contig));
        // Limit both entry count and per-entry coverage to bound memory.
        if value.0.len() > 1000 {
            return value;
        }
        let mut cache = self.overhang_cache.borrow_mut();
        if cache.len() >= 256 {
            cache.clear();
        }
        cache.insert(key.to_vec(), Rc::clone(&value));
        value
    }
}

#[cfg(test)]
mod tests;
