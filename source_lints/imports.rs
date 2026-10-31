use std::path::Path;

pub fn check(path: &Path, source: &str, issues: &mut Vec<String>) {
    let directory = path.parent().unwrap();
    for (index, line) in source.lines().enumerate() {
        let statement = line.trim();
        if statement.starts_with("#[path") || statement.contains("include!(") {
            if let Some(source_path) = statement.split('"').nth(1) {
                if source_path.contains('/') || source_path.contains("..") {
                    issues.push(format!("{}:{}: nested module source", path.display(), index + 1));
                }
            }
        }
        let statement = statement.strip_prefix("pub ").unwrap_or(statement);
        let statement = if statement.starts_with("pub(") {
            statement.split_once(')').map(|(_, rest)| rest.trim()).unwrap_or(statement)
        } else { statement };
        let Some(import) = statement.strip_prefix("use ") else { continue };
        let import = import.trim_end_matches(';');
        let mut parts = import.split("::").map(str::trim);
        let Some(head) = parts.next() else { continue };
        let mut module_dir = match head {
            "super" => directory.to_path_buf(),
            "self" => directory.to_path_buf(),
            "crate" => directory.ancestors().find(|p| p.ends_with("src"))
                .unwrap_or(directory).to_path_buf(),
            _ if directory.join(head).is_dir() || directory.join(head).with_extension("rs").exists()
                => directory.to_path_buf(),
            _ => continue,
        };
        if head == "super" && import.starts_with("super::super::") {
            issues.push(format!("{}:{}: parent-of-parent import", path.display(), index + 1));
            continue;
        }
        let mut hops = 0;
        for part in parts {
            let item = part.trim_start_matches('{').trim_end_matches('}');
            if item.is_empty() || item.contains(',') || item.contains(' ') { break; }
            let nested = module_dir.join(item);
            if nested.is_dir() || nested.with_extension("rs").exists() {
                hops += 1;
                module_dir = nested;
            } else {
                break;
            }
        }
        if hops > 1 || head == "crate" && directory != module_dir && hops > 0 {
            issues.push(format!("{}:{}: nested module import", path.display(), index + 1));
        }
    }
}
