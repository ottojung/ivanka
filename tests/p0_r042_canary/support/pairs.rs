use std::path::Path;

type Pair = (String, String);

pub fn write_pairs(dir: &Path, r1: &[Pair], r2: &[Pair]) {
    for (name, rows) in [("R1", r1), ("R2", r2)] {
        let body = rows
            .iter()
            .map(|(id, seq)| format!("@{id}\n{seq}\n+\n{}\n", "I".repeat(seq.len())))
            .collect::<String>();
        std::fs::write(dir.join(format!("{name}.fastq")), body).unwrap();
    }
}

pub fn read_pairs(
    dominant: &str,
    dom_step: usize,
    sparse: &str,
    sparse_step: usize,
) -> (Vec<Pair>, Vec<Pair>) {
    let mut r1 = Vec::new();
    let mut r2 = Vec::new();
    for (tag, source, step) in [("d", dominant, dom_step), ("a", sparse, sparse_step)] {
        if source.len() < 180 {
            continue;
        }
        for (index, start) in (0..source.len() - 180).step_by(step).enumerate() {
            let id = format!("{tag}{index}");
            r1.push((id.clone(), source[start..start + 90].to_owned()));
            r2.push((id, super::reverse(&source[start + 90..start + 180])));
        }
    }
    (r1, r2)
}
