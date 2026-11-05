import csv, json, tempfile, unittest
from pathlib import Path
from marker_guarded_remap import guarded_project, _lost_marker_loci

def w(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path,'w',newline='') as f:
        wr=csv.DictWriter(f, fieldnames=fieldnames); wr.writeheader(); wr.writerows(rows)

class T(unittest.TestCase):
    def test_noop_without_mapping(self):
        with tempfile.TemporaryDirectory() as d:
            b=Path(d)/'b'; c=Path(d)/'c'; o=Path(d)/'o.csv'
            refs=[{'region':'1-HCV-1a','sequence':'A'*1200}]
            rf=['region','sequence']
            w(b/'scratch/remap_conseq.csv',rf,refs); w(c/'scratch/remap_conseq.csv',rf,refs)
            sam=['qname','flag','rname','pos','mapq','cigar','rnext','pnext','tlen','seq','qual']
            rows=[dict(qname='r1',flag='99',rname='1-HCV-1a',pos='1',mapq='60',cigar='100M',rnext='=',pnext='200',tlen='300',seq='A'*100,qual='I'*100),
                  dict(qname='r1',flag='147',rname='1-HCV-1a',pos='200',mapq='60',cigar='100M',rnext='=',pnext='1',tlen='-300',seq='A'*100,qual='I'*100)]
            w(b/'scratch/remap.csv',sam,rows); w(c/'scratch/remap.csv',sam,rows)
            nuc=['sample','seed','region','q-cutoff','query.nuc.pos','refseq.nuc.pos','genome.pos','A','C','G','T','N','del','ins','clip','v3_overlap','coverage']
            w(b/'nuc.csv',nuc,[dict(sample='s',seed='HCV-1a',region='R',**{'q-cutoff':'15','query.nuc.pos':'1','refseq.nuc.pos':'1','genome.pos':'1','A':'10','C':'90','G':'0','T':'0','N':'0','del':'0','ins':'0','clip':'0','v3_overlap':'0','coverage':'100'})])
            w(c/'nuc.csv',nuc,[dict(sample='s',seed='HCV-1a',region='R',**{'q-cutoff':'15','query.nuc.pos':'1','refseq.nuc.pos':'1','genome.pos':'1','A':'9','C':'91','G':'0','T':'0','N':'0','del':'0','ins':'0','clip':'0','v3_overlap':'0','coverage':'100'})])
            s=guarded_project(b,c,o)
            self.assertEqual(s['pairs_restored'],0)
            self.assertEqual(o.read_bytes(), (c/'scratch/remap.csv').read_bytes())
            self.assertEqual(s['lost_q15_marker_loci'],1)

if __name__=='__main__': unittest.main()
