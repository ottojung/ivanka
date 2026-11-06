"""Read-only experiment: replay existing original mate alignments on exact references.

No original read duplication, no imputed haplotype phase, and no remap
reference mutation. Candidate reference sequence must exactly match the
baseline reference, not merely have a similar alignment score.
"""
import csv
from collections import Counter, defaultdict
from pathlib import Path

from snv_q15_evidence import reverse_complement
from original_fastq_identity import both_alignments_match_original

FIELDS = ('qname','flag','rname','pos','mapq','cigar','rnext','pnext',
          'tlen','seq','qual')


def rows_from_file(path):
    with Path(path).open(newline='') as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError('Unexpected remap CSV format')
        return list(reader)


def mate_number(row):
    flag = int(row['flag'])
    if not flag & 1 or not flag & 2 or flag & (4|8|256|2048):
        return None
    if bool(flag & 64) == bool(flag & 128):
        return None
    return 1 if flag & 64 else 2


def original_pairs(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row['qname']].append(row)
    accepted = {}
    for qname, observations in groups.items():
        if not qname or len(observations) != 2:
            continue
        a, b = observations
        first, second = mate_number(a), mate_number(b)
        if {first, second} != {1, 2} or a['rname'] != b['rname']:
            continue
        accepted[qname] = {first:a, second:b}
    return accepted

def raw_mate_number(row):
    flag = int(row['flag'])
    if not flag & 1 or flag & (256 | 2048):
        return None
    if bool(flag & 64) == bool(flag & 128):
        return None
    return 1 if flag & 64 else 2


def raw_mate_pairs(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row['qname']].append(row)
    result = {}
    for name, items in groups.items():
        if not name or len(items) != 2:
            continue
        first, second = (raw_mate_number(row) for row in items)
        if {first, second} == {1, 2}:
            result[name] = {first: items[0], second: items[1]}
    return result


def same_original_mate(a, b):
    if raw_mate_number(a) != raw_mate_number(b):
        return False
    opposite = bool(int(a['flag']) & 16) != bool(int(b['flag']) & 16)
    if opposite:
        return (a['seq'] == reverse_complement(b['seq'])
                and a['qual'] == b['qual'][::-1])
    return a['seq'] == b['seq'] and a['qual'] == b['qual']


def valid_baseline_alignment(row, reference):
    import re
    try:
        ops = [(int(number), op) for number, op in
               re.findall(r'([1-9]\d*)([MIDS])', row['cigar'])]
        if not ops or ''.join(str(n)+op for n,op in ops) != row['cigar']:
            return False
        if not any(op=='M' for _,op in ops):
            return False
        if any(op=='S' and 0 < i < len(ops)-1
               for i,(_,op) in enumerate(ops)):
            return False
        if any(ops[i][1]=='S' and ops[i+1][1]=='S'
               for i in range(len(ops)-1)):
            return False
        read_length=sum(n for n,op in ops if op in 'MIS')
        reference_length=sum(n for n,op in ops if op in 'MD')
        start=int(row['pos'])-1
        return (start>=0 and start+reference_length<=len(reference)
                and read_length==len(row['seq'])==len(row['qual'])
                and row['rnext'] in ('=',row['rname']))
    except (TypeError,ValueError,KeyError):
        return False


def unique_sequence_targets(candidate_references):
    inverse = defaultdict(list)
    for name, seq in candidate_references.items():
        inverse[seq].append(name)
    return inverse

def project_original_pairs(baseline_rows, baseline_refs,
                           candidate_rows, candidate_refs,
                           *, restore_same_reference_drift=False, restore_improper_pairs=False,
                           original_fastq_pairs=None):
    inverse = unique_sequence_targets(candidate_refs)
    before = original_pairs(baseline_rows)
    after = original_pairs(candidate_rows)
    replacements = {}
    statistics = Counter()
    for qname, current_pair in after.items():
        prior_pair = before.get(qname)
        if prior_pair is None:
            continue
        old_name = prior_pair[1]['rname']
        new_name = current_pair[1]['rname']
        reference = baseline_refs.get(old_name)
        current_reference = candidate_refs.get(new_name)
        if reference is None or current_reference is None:
            statistics['unknown_reference'] += 1
            continue
        same_reference = reference == current_reference
        if same_reference:
            statistics['already_same_reference_sequence'] += 1
            if not restore_same_reference_drift:
                continue
            if all(
                prior_pair[i][field] == current_pair[i][field]
                for i in (1, 2)
                for field in ('pos', 'cigar', 'flag', 'seq', 'qual', 'tlen')
            ):
                continue
            statistics['same_reference_alignment_drift_seen'] += 1
        else:
            statistics['changed_reference_sequence'] += 1
        destinations = inverse.get(reference, ())
        if len(destinations) != 1:
            statistics['no_unique_byte_identical_target'] += 1
            continue
        if not all(same_original_mate(prior_pair[i],current_pair[i])
                   for i in (1,2)):
            if not both_alignments_match_original(
                    prior_pair,current_pair,
                    (original_fastq_pairs or {}).get(qname)):
                statistics['different_original_mate_bytes'] += 1
                continue
            statistics['verified_trimmed_or_reoriented_original_pair'] += 1
        if not all(valid_baseline_alignment(prior_pair[i], reference)
                   for i in (1,2)):
            statistics['unsupported_baseline_alignment'] += 1
            continue
        candidate_target = destinations[0]
        mapped = {}
        for mate in (1,2):
            old, new = prior_pair[mate], current_pair[mate]
            row = old.copy()
            row['rname'] = candidate_target
            if row['rnext'] == old_name:
                row['rnext'] = candidate_target
            row['mapq'] = str(min(int(old['mapq']),int(new['mapq'])))
            mapped[mate] = row
        replacements[qname] = mapped
        statistics['restored_original_pairs'] += 1
        if same_reference:
            statistics['same_reference_alignment_drift_restored'] += 1
        if any(bool(int(prior_pair[i]['flag'])&16) !=
               bool(int(current_pair[i]['flag'])&16) for i in (1,2)):
            statistics['reverse_oriented_pairs_restored'] += 1
    if restore_improper_pairs:
        original_raw = raw_mate_pairs(candidate_rows)
        for qname in sorted(before.keys() - after.keys()):
            prior_pair = before[qname]
            observed_pair = original_raw.get(qname)
            if observed_pair is None:
                statistics['baseline_strict_pair_missing_in_candidate_raw'] += 1
                continue
            original_name = prior_pair[1]['rname']
            reference = baseline_refs.get(original_name)
            destinations = inverse.get(reference, ()) if reference else ()
            if len(destinations) != 1:
                statistics['improper_pair_without_unique_exact_reference'] += 1
                continue
            if not all(same_original_mate(prior_pair[i], observed_pair[i])
                       for i in (1,2)):
                if not both_alignments_match_original(
                        prior_pair,observed_pair,
                        (original_fastq_pairs or {}).get(qname)):
                    statistics['improper_pair_mate_bytes_changed'] += 1
                    continue
                statistics['verified_improper_trimmed_original_pair'] += 1
            if not all(valid_baseline_alignment(prior_pair[i], reference)
                       for i in (1,2)):
                statistics['improper_pair_baseline_alignment_invalid'] += 1
                continue
            target = destinations[0]
            replacements[qname] = {}
            for i in (1,2):
                row = prior_pair[i].copy()
                row['rname'] = target
                if row['rnext'] == original_name:
                    row['rnext'] = target
                row['mapq'] = str(min(int(row['mapq']),
                                     int(observed_pair[i]['mapq'])))
                replacements[qname][i] = row
            statistics['improper_original_pairs_restored'] += 1
    result = []
    for row in candidate_rows:
        replacement = replacements.get(row['qname'])
        result.append((replacement[raw_mate_number(row)].copy()
                       if replacement else row.copy()))
    if (len(result) != len(candidate_rows)
            or Counter(r['qname'] for r in result) !=
               Counter(r['qname'] for r in candidate_rows)):
        raise AssertionError('Attempted change to original read multiplicity')
    return result, dict(statistics)
