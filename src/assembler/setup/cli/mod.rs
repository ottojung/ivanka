use super::audit_guard::validate_audit;
mod finish;
mod options;
use options::Args;

mod config;
mod help;
pub(crate) use config::Config;
/// Parse the fixed CLI contract and validate every optional output path
/// before loading reads or creating an output file.
pub(crate) fn parse() -> Result<Config, String> {
    let args = std::env::args().collect::<Vec<_>>();
    let mut parsed = Args {
        max: 16,
        ..Args::default()
    };
    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            flag @ ("--reads1"
            | "--reads2"
            | "--output"
            | "--max-contigs"
            | "--max-pairs"
            | "--seeds"
            | "--unphased-snv-audit")
                if i + 1 < args.len() =>
            {
                parsed.apply(flag, &args[i + 1])?;
                i += 2;
            }
            "--help" | "-h" => {
                help::show();
                std::process::exit(0);
            }
            _ => return Err(format!("unknown/incomplete argument: {}", args[i])),
        }
    }
    parsed.finish()
}
