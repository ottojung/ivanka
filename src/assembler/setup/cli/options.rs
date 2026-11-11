#[derive(Default)]
pub(super) struct Args {
    pub(super) a: Option<String>,
    pub(super) b: Option<String>,
    pub(super) output: Option<String>,
    pub(super) max: usize,
    pub(super) max_pairs: Option<usize>,
    pub(super) seeds: Option<String>,
    pub(super) snv_audit: Option<String>,
}

impl Args {
    pub(super) fn apply(&mut self, flag: &str, value: &str) -> Result<(), String> {
        match flag {
            "--reads1" => self.a = Some(value.to_owned()),
            "--reads2" => self.b = Some(value.to_owned()),
            "--output" => self.output = Some(value.to_owned()),
            "--max-contigs" => self.max = value.parse().map_err(|_| "invalid max-contigs")?,
            "--max-pairs" => self.max_pairs = Some(value.parse().map_err(|_| "invalid max-pairs")?),
            "--seeds" => self.seeds = Some(value.to_owned()),
            "--unphased-snv-audit" => self.snv_audit = Some(value.to_owned()),
            _ => unreachable!("only recognized options reach the parser"),
        }
        Ok(())
    }
}
