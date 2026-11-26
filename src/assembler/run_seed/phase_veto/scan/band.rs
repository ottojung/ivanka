// Row offsets of the usable (i, j) variant pairs: j > i and
// var[j] - var[i] <= max_span. `off[i]..off[i+1]` is one row; pairs outside
// the band can never acquire ref or signature evidence, so they are not
// allocated. The layout is deterministic and independent of read order.
pub(super) fn build(var: &[usize], max_span: usize) -> Vec<usize> {
    let nv = var.len();
    let mut off = vec![0usize; nv + 1];
    let mut j = 1usize;
    for i in 0..nv {
        if j < i + 1 {
            j = i + 1;
        }
        while j < nv && var[j] - var[i] <= max_span {
            j += 1;
        }
        off[i + 1] = off[i] + (j - i - 1);
    }
    off
}

#[inline]
pub(super) fn slot(off: &[usize], i: usize, j: usize) -> Option<usize> {
    if j <= i {
        return None;
    }
    let row = off[i + 1] - off[i];
    if j - i > row {
        return None;
    }
    Some(off[i] + j - i - 1)
}

#[cfg(test)]
mod tests {
    use super::{build, slot};

    #[test]
    fn band_allocates_only_in_span_pairs() {
        let var: Vec<usize> = (0..40).map(|k| 12 + k * 80).collect();
        let off = build(&var, 400);
        assert_eq!(off.len(), 41);
        assert_eq!(off[40], 185);
        assert!(off[40] < 40 * 40);
        assert_eq!(slot(&off, 0, 5), Some(4));
        assert_eq!(slot(&off, 0, 6), None);
        assert_eq!(slot(&off, 39, 40), None);
    }
}
