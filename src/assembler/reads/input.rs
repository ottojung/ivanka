
use flate2::read::MultiGzDecoder;
use std::fs::File;
use std::io::{self, BufRead, BufReader};

pub(crate) fn read_open(path: &str) -> io::Result<Box<dyn BufRead>> {
    let f = File::open(path)?;
    if path.ends_with(".gz") {
        Ok(Box::new(BufReader::new(MultiGzDecoder::new(f))))
    } else { Ok(Box::new(BufReader::new(f))) }
}
