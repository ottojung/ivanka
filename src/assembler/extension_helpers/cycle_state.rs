use std::collections::HashMap;
use super::cycle::{next_anchor, repeats, CYCLE_MATCH, CYCLE_MIN_SPACING};

// Reuse scanned anchors while a contig only grows on the right. Any
// left prepend invalidates positions and requires an exact full rescan.
// A repeat found wholly inside the already assembled path must never erase
// that path's phased sequence when a new extension triggers a cycle scan.
pub(crate) fn cycle_cut_keeps_prior_path(cut:usize,left:usize,prior:usize)->bool {
    cut>=left.saturating_add(prior)
}

pub(crate) struct CycleTracker {
    first: HashMap<u64,usize>,
    scanned: usize,
    previous: Option<u64>,
}
impl CycleTracker {
    pub(crate) fn new()->Self {
        Self{first:HashMap::new(),scanned:0,previous:None}
    }
    pub(crate) fn check(&mut self, seq:&[u8], k:usize,
                         encode:fn(&[u8])->Option<u64>, prepended:bool)->Option<usize> {
        if prepended {
            self.first.clear();self.scanned=0;self.previous=None;
        }
        if seq.len()<CYCLE_MIN_SPACING+CYCLE_MATCH {return None;}
        for i in self.scanned..=seq.len()-CYCLE_MATCH {
            let anchor=next_anchor(seq,i,k,self.previous,encode);
            self.previous=anchor;
            let Some(anchor)=anchor else {continue;};
            if let Some(&j)=self.first.get(&anchor) {
                if repeats(seq,j,i,k,encode) {return Some(i+CYCLE_MATCH);}
            } else {self.first.insert(anchor,i);}
        }
        self.scanned=seq.len()-CYCLE_MATCH+1;
        None
    }
}
