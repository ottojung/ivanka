mod imports;
mod lines;
mod tree;

use std::path::Path;

pub fn check(root: &Path) {
    let mut violations = Vec::new();
    tree::visit(&root.join("src"), &mut violations);
    tree::visit(&root.join("source_lints"), &mut violations);
    let build = root.join("build.rs");
    if let Ok(source) = std::fs::read_to_string(&build) {
        let count = lines::code_lines(&source);
        if count > 50 {
            violations.push(format!("build.rs: {count} code LOC exceeds 50"));
        }
        imports::check(&build, &source, &mut violations);
    }
    if !violations.is_empty() {
        for violation in &violations {
            eprintln!("Rust structural lint: {violation}");
        }
        panic!("{} Rust structural lint violations", violations.len());
    }
}

#[cfg(test)]
mod tests;
