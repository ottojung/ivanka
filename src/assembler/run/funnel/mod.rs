#[cfg(test)]
mod tests;
use super::{canonical_kmer, K};
use std::fs::OpenOptions;
use std::io::{self, Write};
use std::os::unix::fs::OpenOptionsExt;
use std::path::PathBuf;

const MAX_ENTRIES: usize = 32;
const MAX_BASES: usize = 65536;

fn open(path: PathBuf) -> io::Result<std::fs::File> {
    OpenOptions::new().create(true).append(true).mode(0o600).open(path)
}

fn hash(data: &[u8]) -> String {
    let mut value = 0xcbf29ce484222325u64;
    for &byte in data {
        value = (value ^ u64::from(byte)).wrapping_mul(0x100000001b3);
    }
    format!("{value:016x}")
}

/// Append one bounded funnel stage to a private trace and a sequence-free summary.
/// Both files are derived only from the existing output path; no env or CLI option.
pub(super) fn emit(out: &str, stage: &str, entries: &[(usize, &[u8], usize)]) -> io::Result<()> {
    let mut private = open(PathBuf::from(format!("{out}.ouj-funnel-private.jsonl")))?;
    let mut summary = open(PathBuf::from(format!("{out}.ouj-funnel-summary.jsonl")))?;
    let mut rows = entries.to_vec();
    rows.sort_by_key(|row| row.0);
    write!(private, "{{\"s\":\"{stage}\",\"e\":[")?;
    write!(summary, "{{\"s\":\"{stage}\",\"e\":[")?;
    for (n, (index, seq, support)) in rows.iter().take(MAX_ENTRIES).enumerate() {
        let stored = seq.len().min(MAX_BASES);
        let head = format!(
            "{{\"i\":{index},\"l\":{},\"s\":{support},\"h\":\"{}\",\"k\":{},\"q\":\"{}\",\"stored\":{stored}",
            seq.len(),
            hash(seq),
            seq.windows(K).filter_map(canonical_kmer).count(),
            if seq.len() > MAX_BASES { "t" } else { "f" }
        );
        if n > 0 {
            write!(private, ",")?;
            write!(summary, ",")?;
        }
        write!(private, "{head},\"seq\":\"{}\"}}", String::from_utf8_lossy(&seq[..stored]))?;
        write!(summary, "{head}}}")?;
    }
    writeln!(private, "]}}")?;
    writeln!(summary, "]}}")
}
