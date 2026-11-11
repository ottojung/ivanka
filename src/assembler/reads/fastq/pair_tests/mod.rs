use super::mate_headers;
use super::{FastqSeqReader, Reads};
use std::{
    fs,
    io::{Cursor, ErrorKind},
};

mod headers;
mod loading;
mod readers;
