use super::rc;

// Suppress only the same complete path, in either DNA orientation.
// Shared k-mers alone do not establish that a phased haplotype is redundant.
pub(crate) fn contained_path(existing:&[Vec<u8>], candidate:&[u8])->bool {
    if candidate.is_empty() {return true;}
    let reverse=rc(candidate);
    existing.iter().any(|contig|contig.windows(candidate.len())
        .any(|window|window==candidate || window==reverse))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn reverse_complement_is_not_a_second_haplotype() {
        let seq=b"ACGTTGACCTAACGATGCTAGTCCATGACGTT";
        assert!(contained_path(&[seq.to_vec()],&rc(seq)));
    }
    #[test] fn phased_substitution_survives_shared_flanks() {
        let original=b"ACGTTGACCTAACGATGCTAGTCCATGACGTT";
        let mut variant=original.to_vec();
        variant[16]=b'A';
        assert!(!contained_path(&[original.to_vec()],&variant));
        assert!(!contained_path(&[original.to_vec()],&rc(&variant)));
    }
    #[test] fn full_length_containment_only() {
        let full=b"ACGTTGACCTAACGATGCTAGTCCATGACGTT";
        assert!(contained_path(&[full.to_vec()],&full[4..29]));
        assert!(!contained_path(&[full[4..29].to_vec()],full));
    }
}
