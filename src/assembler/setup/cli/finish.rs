use super::options::Args;
use super::{validate_audit, Config};

impl Args {
    pub(super) fn finish(self) -> Result<Config, String> {
        if self.max == 0 || self.max > 1000 {
            return Err("max-contigs must be in 1..=1000".to_string());
        }
        let out = self.output.ok_or("missing --output")?;
        validate_audit(
            self.a.as_deref(),
            self.b.as_deref(),
            self.seeds.as_deref(),
            &out,
            self.snv_audit.as_deref(),
        )?;
        Ok(Config {
            reads1: self.a.ok_or("missing --reads1")?,
            reads2: self.b.ok_or("missing --reads2")?,
            output: out,
            max_contigs: self.max,
            max_pairs: self.max_pairs,
            seeds: self.seeds,
            audit: self.snv_audit,
        })
    }
}
