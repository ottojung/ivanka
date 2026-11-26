pub(crate) const A: usize = 25;
pub(crate) type K128 = u128;
pub(crate) const INV: u64 = u64::MAX;

pub(crate) fn kcodes(seq: &[u8], a: usize) -> Vec<u64> {
    let mut out = vec![INV; seq.len().saturating_sub(a.saturating_sub(1))];
    let (mut f, mut v, mask) = (0u64, 0usize, (1u64 << (2 * a)) - 1);
    for (i, &b) in seq.iter().enumerate() {
        let d = match b {
            b'A' => 0,
            b'C' => 1,
            b'G' => 2,
            b'T' => 3,
            _ => {
                f = 0;
                v = 0;
                continue;
            }
        };
        f = ((f << 2) & mask) | d;
        v += 1;
        if v >= a {
            out[i + 1 - a] = f;
        }
    }
    out
}

pub(crate) fn validw(p: &[usize], s: usize, e: usize) -> bool {
    e < p.len() && s <= e && p[s] == p[e]
}

pub(crate) fn encode_a(seq: &[u8]) -> Option<u64> {
    let mut n = 0u64;
    for &b in seq {
        n = (n << 2)
            | match b {
                b'A' => 0,
                b'C' => 1,
                b'G' => 2,
                b'T' => 3,
                _ => return None,
            };
    }
    Some(n)
}
