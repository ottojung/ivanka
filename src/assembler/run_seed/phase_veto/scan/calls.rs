use super::{validw, FlankIndex, Prep, A, INV, K128};

// Dense, position-sorted call list: the placement offset is fixed once the
// first unique flank matches, so every later flank adds a distinct position.
pub(super) struct Calls {
    pub st: isize,
    pub en: isize,
    pub pairs: Vec<(usize, u8)>,
}

pub(super) fn locate(read: &[u8], prep: &Prep, index: &FlankIndex) -> Option<Calls> {
    if read.len() < 2 * A + 1 || read.len() != prep.lq.len().saturating_sub(1) {
        return None;
    }
    let mut st = None;
    let mut pairs = Vec::new();
    for i in 0..=read.len().saturating_sub(2 * A + 1) {
        if !validw(&prep.lq, i, i + 2 * A + 1) || i + A + 1 >= prep.km.len() {
            continue;
        }
        let (l, r) = (prep.km[i], prep.km[i + A + 1]);
        if l == INV || r == INV {
            continue;
        }
        let key = ((l as K128) << (2 * A)) | (r as K128);
        let Some(Some(pos)) = index.get(&key) else {
            continue;
        };
        let place = *pos as isize - (i + A) as isize;
        if place < 0 || st.is_some_and(|s| s != place) {
            return None;
        }
        st = Some(place);
        pairs.push((*pos, read[i + A]));
    }
    if pairs.len() < 2 {
        return None;
    }
    let st = st?;
    Some(Calls {
        st,
        en: st + read.len() as isize,
        pairs,
    })
}
