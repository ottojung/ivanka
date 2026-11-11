"""Blinded Q15 two-locus links from original FASTQ, not known haplotypes.

Reference template and two variant coordinates specify local DNA loci only.
No assembled contig or generating phase is read. Observed pair IDs and
paired sequences are different evidence classes, never molecule counts.
"""
from collections import Counter, defaultdict

from snv_q15_evidence import reverse_complement

DNA = 'ACGT'


def local_words(template, position, flank=15):
    if (type(position) is not int or type(flank) is not int or flank < 1
            or position < flank or position + flank >= len(template)
            or any(base not in DNA for base in template)):
        raise ValueError('Invalid unambiguous reference and local position')
    left, right = template[position-flank:position], template[position+1:position+flank+1]
    return {base:left+base+right for base in DNA}


def mate_observes(mate, word, min_phred):
    bases, qualities = mate
    for candidate in (word, reverse_complement(word)):
        index = bases.find(candidate)
        while index != -1:
            if all(ord(q)-33 >= min_phred for q in qualities[index:index+len(word)]):
                return True
            index = bases.find(candidate,index+1)
    return False


def allele_at_pair(mate1, mate2, words, min_phred):
    found = [base for base,word in words.items()
             if mate_observes(mate1,word,min_phred)
             or mate_observes(mate2,word,min_phred)]
    return found[0] if len(found)==1 else None


def direct_source_links(template, positions, pairs, *, min_phred=15):
    if (len(positions)!=2 or positions[0]>=positions[1]
            or type(min_phred) is not int or not 0 <= min_phred <= 60):
        raise ValueError('Two ordered distinct sites and Phred 0..60 required')
    contexts=[local_words(template,site) for site in positions]
    for pos, words in zip(positions,contexts):
        for base, word in words.items():
            # Full-read evidence cannot localize a 31-mer repeated elsewhere
            # in the template. Only the reference allele may occur once.
            hits = template.count(word) + template.count(reverse_complement(word))
            if hits != (1 if base == template[pos] else 0):
                raise ValueError('Repeated or nonlocal 31-mer allele anchor')
    # A word matching both loci (on either strand) is not a link.
    # Every direct event must have two distinguishable local anchors.
    canonical=lambda word:min(word,reverse_complement(word))
    if ({canonical(word) for word in contexts[0].values()}
            & {canonical(word) for word in contexts[1].values()}):
        raise ValueError('Ambiguous repeated or strand-symmetric locus anchors')
    signature_counts=Counter()
    signature_events=defaultdict(list)
    direct_pairs=Counter()
    single_sites=[Counter(),Counter()]
    seen_qnames=set()
    total=0
    for name,mate1,mate2 in pairs:
        if not name or name in seen_qnames:
            raise ValueError('Original paired read identifiers must be unique')
        seen_qnames.add(name)
        total+=1
        bases=tuple(allele_at_pair(mate1,mate2,words,min_phred)
                    for words in contexts)
        for site,base in enumerate(bases):
            if base is not None:
                single_sites[site][base]+=1
        event=bases if all(base is not None for base in bases) else None
        if event is not None:
            direct_pairs[event]+=1
        signature=(mate1[0],mate2[0])
        signature_counts[signature]+=1
        signature_events[signature].append(event)
    signatures=Counter()
    incomplete_signatures=0
    inconsistent_signatures=0
    for signature,events in signature_events.items():
        if any(event is None for event in events):
            incomplete_signatures+=1
        elif len(set(events))!=1:
            inconsistent_signatures+=1
        elif len(events)==signature_counts[signature]:
            signatures[events[0]]+=1
    def counts_by_event(data):
        return {a+b:value for (a,b),value in sorted(data.items())}
    return {
        'schema_version':'ivanka.blinded_original_q15_phase_bridges.v1',
        'positions_zero_based':list(positions),
        'original_pairs_scanned':total,
        'original_pair_direct_link_counts':counts_by_event(direct_pairs),
        'distinct_consistent_paired_sequence_link_counts':
            counts_by_event(signatures),
        'per_site_original_pair_allele_counts':[
            dict(sorted(v.items())) for v in single_sites],
        'incomplete_paired_sequence_signatures_vetoed':incomplete_signatures,
        'inconsistent_paired_sequence_signatures_vetoed':inconsistent_signatures,
        'original_pairs_with_both_loci_observed':sum(direct_pairs.values()),
        'source_haplotype_phase_known':False,
        'full_length_phase_or_molecule_independence_proven':False,
        'absent_direct_event_is_not_a_proof_of_absence':True,
    }


def directly_observed_candidate(alleles, evidence, *, min_pairs=3,
                                min_distinct_signatures=3):
    if (len(alleles)!=2 or any(base not in DNA for base in alleles)
            or type(min_pairs) is not int or min_pairs < 1
            or type(min_distinct_signatures) is not int or min_distinct_signatures < 1):
        raise ValueError('Two valid candidate alleles and positive thresholds required')
    key=''.join(alleles)
    original=evidence['original_pair_direct_link_counts'].get(key,0)
    unique=evidence['distinct_consistent_paired_sequence_link_counts'].get(key,0)
    qualifies=original>=min_pairs and unique>=min_distinct_signatures
    return {
        'candidate_alleles':list(alleles),
        'direct_original_pair_evidence':original,
        'distinct_consistent_paired_sequence_evidence':unique,
        'status': 'directly_observed_local_link' if qualifies else 'unknown',
        'may_delete_contig_or_assign_full_length_phase':False,
    }
