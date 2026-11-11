// Pair only original matching FASTQ IDs; CASAVA and legacy mate formats.
fn parse_header(h: &str) -> Option<(&str, Option<u8>)> {
    let mut words = h.strip_prefix('@')?.split_ascii_whitespace();
    let read = words.next()?;
    let (id, suffix) = if let Some(name) = read.strip_suffix("/1") {
        (name, Some(1))
    } else if let Some(name) = read.strip_suffix("/2") {
        (name, Some(2))
    } else {
        (read, None)
    };
    if id.is_empty() {
        return None;
    }
    let casava = match words.next() {
        Some(w) if w.starts_with("1:") => Some(1),
        Some(w) if w.starts_with("2:") => Some(2),
        Some(w)
            if w.split_once(':').is_some()
                && w.as_bytes().first().is_some_and(u8::is_ascii_digit) =>
        {
            return None
        }
        _ => None,
    };
    if suffix.is_some() && casava.is_some() && suffix != casava {
        return None;
    }
    Some((id, suffix.or(casava)))
}

pub(crate) fn mate_headers(a: &str, b: &str) -> bool {
    match (parse_header(a), parse_header(b)) {
        (Some((name_a, mate_a)), Some((name_b, mate_b))) => {
            name_a == name_b
                && mate_a.is_some() == mate_b.is_some()
                && mate_a != Some(2)
                && mate_b != Some(1)
        }
        _ => false,
    }
}
