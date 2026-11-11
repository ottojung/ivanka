use std::path::Path;

pub(super) fn validate_audit(
    reads1: Option<&str>,
    reads2: Option<&str>,
    seeds: Option<&str>,
    fasta: &str,
    audit: Option<&str>,
) -> Result<(), String> {
    let Some(path) = audit else {
        return Ok(());
    };
    let target = Path::new(path);
    if path == fasta || target.exists() {
        return Err("SNV audit must be a new file distinct from contig FASTA".into());
    }
    let parent = target
        .parent()
        .filter(|dir| !dir.as_os_str().is_empty())
        .unwrap_or(Path::new("."))
        .canonicalize()
        .map_err(|_| "SNV audit parent directory missing".to_string())?;
    for source in [reads1, reads2, seeds].into_iter().flatten() {
        if let Some(dir) = Path::new(source)
            .parent()
            .and_then(|dir| dir.canonicalize().ok())
        {
            if dir == parent {
                return Err("SNV audit cannot write to original read/seed directory".into());
            }
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests;
