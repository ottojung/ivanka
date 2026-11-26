//! Byte-exact packed stats-dump serialization.
//! Field widths are forced by the published 351,376-byte length:
//! 47,820 u32 depth + 6 u64 pairs + 6 u64 coverage + 80,000 u16 masks.
use crate::packed::Stats;

pub const EXPECTED_STATS: &str = "f45f93afa3484e7b3a9f790b9f915b91a5d13ed09967c5446ccf7cf476d6c269";
pub const EXPECTED_FASTA: &str = "f6cc54774995558c7dd8fa27713937e36aa1aa16dc9b62a767d8e73a8d965f3e";
pub const EXPECTED_BYTES: usize = 351_376;

fn put(out: &mut Vec<u8>, bytes: impl IntoIterator<Item = u8>) {
    out.extend(bytes);
}

fn field(stats: &Stats, which: usize, big: bool) -> Vec<u8> {
    let (depth, pairs, coverage, masks) = stats;
    let mut out = Vec::new();
    match which {
        0 => {
            for row in depth {
                for &v in row {
                    if big {
                        put(&mut out, v.to_be_bytes())
                    } else {
                        put(&mut out, v.to_le_bytes())
                    }
                }
            }
        }
        1 | 2 => {
            for &v in if which == 1 { pairs } else { coverage } {
                let n = v as u64;
                if big {
                    put(&mut out, n.to_be_bytes())
                } else {
                    put(&mut out, n.to_le_bytes())
                }
            }
        }
        _ => {
            for &v in masks {
                if big {
                    put(&mut out, v.to_be_bytes())
                } else {
                    put(&mut out, v.to_le_bytes())
                }
            }
        }
    }
    out
}

/// Serialize the four fields in the given order. `[0,1,2,3]` little-endian is
/// the reviewer's independently recomputed 351,376-byte framing.
pub fn serialize(stats: &Stats, order: [usize; 4], big: bool) -> Vec<u8> {
    let mut out = Vec::with_capacity(EXPECTED_BYTES);
    for &which in &order {
        out.extend(field(stats, which, big));
    }
    out
}

pub fn fasta(contigs: &[Vec<u8>]) -> Vec<u8> {
    let mut out = Vec::new();
    for (i, seq) in contigs.iter().enumerate() {
        out.extend(format!(">ivanka_{} len={}\n", i + 1, seq.len()).bytes());
        out.extend(seq);
        out.push(b'\n');
    }
    out
}
