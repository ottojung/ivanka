"""Coherent reference-kmer support, not aggregate cross-reference hits."""
from collections import Counter,defaultdict
from ivanka_reference_selector import COMPLEMENT

def build_position_index(references,k=21):
    hits=defaultdict(list)
    for rid, (_,seq) in enumerate(references):
        for i in range(len(seq)-k+1):
            key=seq[i:i+k]
            if len(key)==k and set(key)<=set("ACGT"):
                hits[key].append((rid,i))
    return dict(hits)

def diagonal_support(seq,index,k=21):
    seq=seq.upper()
    best=0
    for source in (seq,seq.translate(COMPLEMENT)[::-1]):
        count=Counter()
        for pos in range(len(source)-k+1):
            motif=source[pos:pos+k]
            locations=index.get(motif,())
            if len(locations)>64:
                continue
            for ref_id,ref_pos in locations:
                key=(ref_id,ref_pos-pos)
                count[key]+=1
                if count[key]>best:best=count[key]
    return best

def rank_diagonal(entries,index,k=21):
    vals=[diagonal_support(seq,index,k) for _,seq in entries]
    order=sorted(range(len(entries)),key=lambda i:(-vals[i],-len(entries[i][1]),i))
    return [(i,len(entries[i][1]),vals[i]) for i in order]


def preserve_original_order(entries, ranking, limit):
    if not 1 <= limit <= 1000:
        raise ValueError("Invalid native-order selection limit")
    chosen = sorted(ranking[:limit], key=lambda item: item[0])
    return [entries[i] for i, _, _ in chosen], [score for _, _, score in chosen]
