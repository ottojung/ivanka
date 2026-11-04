// Experimental ambiguous-sequence alternative to fragmenting a contig.
use super::{collect::observations,detect::incompatible_link};
pub(crate) fn mask_unsupported_contigs(contigs: Vec<Vec<u8>>,
    reads: &[Vec<u8>],qualities:&[Vec<u8>]) -> Vec<Vec<u8>> {
    contigs.into_iter().enumerate().map(|(i,mut seq)| {
        let mut masked=0usize;
        for _ in 0..16 {
            let calls=observations(&seq,reads,qualities,25);
            let Some((p,q,n))=incompatible_link(&seq,reads,&calls) else {break;};
            let coverage=|site:usize|calls.iter().filter(|c|c.contains_key(&site)).count();
            let site=if coverage(p)<coverage(q) {p}else{q};
            if site>=seq.len() || !b"ACGT".contains(&seq[site]) {break;}
            seq[site]=b'N';masked+=1;
            eprintln!("EXPERIMENTAL_PHASE_MASK contig={} unresolved phase at site={} after {} distinct conflicting paired sequences; no full haplotype claim",i+1,site,n);
        }
        if masked==16 && incompatible_link(&seq,reads,
            &observations(&seq,reads,qualities,25)).is_some() {
            eprintln!("EXPERIMENTAL_PHASE_MASK incomplete after 16 ambiguous sites; contig remains unsafe to interpret as a phased haplotype");
        }
        seq
    }).collect()
}
