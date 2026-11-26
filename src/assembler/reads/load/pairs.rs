use super::{count_sampled_seed_kmers, io, mate_headers, rc, read_open, FastqSeqReader, HashMap};
/// Load mates together, rejecting unequal counts or mismatched identities.
/// Each original read is followed by its reverse complement in the index.
/// Seed-depth sampling is bounded independently of the number of indexed pairs.
pub(super) fn parse_pairs(fq1: &str, fq2: &str, max_pairs: Option<usize>) -> io::Result<super::LoadedPairs> {
    let (mut r1, mut r2) = (FastqSeqReader::new(read_open(fq1)?), FastqSeqReader::new(read_open(fq2)?));
    let (mut seqs, mut quals, mut seed_counts, mut pairs) = (Vec::new(), Vec::new(), HashMap::new(), 0usize);
    loop {
        if max_pairs.is_some_and(|m| pairs >= m) { break; }
        let (a, b) = (r1.read_seq()?, r2.read_seq()?);
        let mismatch = a.is_some() != b.is_some();
        let (Some((a, aq)), Some((b, bq))) = (a, b) else {
            if mismatch { return Err(io::Error::new(io::ErrorKind::InvalidData, "unequal mate counts")); }
            break;
        };
        if !mate_headers(&r1.header, &r2.header) {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "FASTQ read-pair IDs or mate designators disagree"));
        }
        for (read, qual) in [(a, aq), (b, bq)] {
            super::validate::indexed_length(&read)?;
            if pairs < 50000 { count_sampled_seed_kmers(&read, &mut seed_counts); }
            let mut rqual = qual.clone(); rqual.reverse();
            let reverse = rc(&read);
            seqs.push(read); quals.push(qual); seqs.push(reverse); quals.push(rqual);
        }
        pairs += 1;
        if pairs.is_multiple_of(1000000) { eprintln!("loaded {} read pairs", pairs); }
    }
    Ok((seqs, quals, seed_counts, pairs))
}
