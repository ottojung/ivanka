use std::rc::Rc;
use super::Reads;
impl Reads {
    // Any extending read overlaps fewer than max_read_len bases, so all
    // successful anchors depend only on this exact suffix (or the whole
    // sequence when shorter); their traversal order is also unchanged.
    pub(crate) fn cached_overhangs(&self,contig:&[u8])->Rc<(Vec<Vec<u8>>,Vec<u32>)> {
        let key=&contig[contig.len().saturating_sub(self.max_read_len)..];
        if let Some(v)=self.overhang_cache.borrow().get(key) {return Rc::clone(v);}
        let value=Rc::new(self.overhangs_with_ids(contig));
        let mut cache=self.overhang_cache.borrow_mut();
        if cache.len()>=256 {cache.clear();}
        cache.insert(key.to_vec(),Rc::clone(&value));
        value
    }
}
#[test] fn exact_suffix_cache_matches_fresh_query() {
    let contig=b"ACGT".repeat(100);
    let mut read=contig[290..].to_vec();read.extend_from_slice(b"AG");
    let reads=Reads{max_read_len:read.len(),seqs:vec![read.clone()],
        index:super::build_index(&[read]),seed_counts:Default::default(),
        overhang_cache:Default::default(),overlength_rejections:Default::default()};
    let original=reads.cached_overhangs(&contig);
    let mut extended=b"TGCA".repeat(20);extended.extend_from_slice(&contig);
    let repeated=reads.cached_overhangs(&extended);
    assert!(Rc::ptr_eq(&original,&repeated));
    assert!(!original.0.is_empty());
    assert_eq!(*original,reads.overhangs_with_ids(&extended));
}


#[test] fn short_sequences_have_distinct_keys_and_cache_stays_bounded() {
    let reads=Reads{max_read_len:300,seqs:Vec::new(),index:Default::default(),
        seed_counts:Default::default(),overhang_cache:Default::default(),overlength_rejections:Default::default()};
    let first=reads.cached_overhangs(b"ACGTACGT");
    let second=reads.cached_overhangs(b"TCGTACGT");
    assert!(!Rc::ptr_eq(&first,&second));
    for i in 0..90u32 {reads.cached_overhangs(&i.to_le_bytes());}
    assert!(reads.overhang_cache.borrow().len()<=256);
    assert_eq!(*first,reads.overhangs_with_ids(b"ACGTACGT"));
}
