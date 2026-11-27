use super::{emit, MAX_BASES, MAX_ENTRIES};
use std::fs;
use std::os::unix::fs::PermissionsExt;

fn out(tag: &str) -> String {
    let dir = std::env::temp_dir().join(format!("ouj-funnel-{}", std::process::id()));
    fs::create_dir_all(&dir).unwrap();
    dir.join(tag).to_str().unwrap().to_owned()
}

#[test]
fn entries_are_bounded_and_index_sorted() {
    let base = out("bounds");
    let all: Vec<(usize, &[u8], usize)> = (0..40)
        .map(|i| (39 - i, &b"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"[..], i))
        .collect();
    emit(&base, "native", &all).unwrap();
    let text = fs::read_to_string(format!("{base}.ouj-funnel-summary.jsonl")).unwrap();
    assert_eq!(text.matches("\"i\":").count(), MAX_ENTRIES);
    let first = text.find("\"i\":0").unwrap();
    let second = text.find("\"i\":1,").unwrap();
    assert!(first < second);
}

#[test]
fn truncation_is_accounted_and_sequences_stay_private() {
    let base = out("truncate");
    let seq = vec![b'C'; MAX_BASES + 5];
    emit(&base, "native", &[(0, seq.as_slice(), 7)]).unwrap();
    let private = fs::read_to_string(format!("{base}.ouj-funnel-private.jsonl")).unwrap();
    let summary = fs::read_to_string(format!("{base}.ouj-funnel-summary.jsonl")).unwrap();
    assert!(private.contains("\"q\":\"t\""));
    assert!(private.contains(&format!("\"stored\":{MAX_BASES}")));
    assert!(private.contains(&format!("\"l\":{}", MAX_BASES + 5)));
    assert!(private.contains("\"seq\":\""));
    assert!(!summary.contains("\"seq\""));
    assert_eq!(summary.matches("\"i\":").count(), 1);
}

#[test]
fn repeat_emission_is_byte_identical_and_private_file_is_0600() {
    let (a, b) = (out("repeat-a"), out("repeat-b"));
    let seq = vec![b'G'; 128];
    for base in [&a, &b] {
        emit(base, "tiling_after", &[(0, seq.as_slice(), 3)]).unwrap();
    }
    assert_eq!(
        fs::read(format!("{a}.ouj-funnel-summary.jsonl")).unwrap(),
        fs::read(format!("{b}.ouj-funnel-summary.jsonl")).unwrap()
    );
    let mode = fs::metadata(format!("{a}.ouj-funnel-private.jsonl")).unwrap().permissions().mode();
    assert_eq!(mode & 0o777, 0o600);
}
