mod source_lints;

fn main() {
    println!("cargo:rerun-if-changed=src");
    println!("cargo:rerun-if-changed=source_lints");
    source_lints::check(std::path::Path::new(env!("CARGO_MANIFEST_DIR")));
}
