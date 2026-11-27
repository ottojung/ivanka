"""Browser coverage for the opt-in reference-based remap display contract.

Node-only tests on small synthetic runs: no site deployment, no benchmark
execution and no frozen data are involved. They prove that the method label
travels with the tool and that unavailable de novo-only metrics render as N/A
rather than a fabricated zero in rankings, case tables and the Ψ matrix.
"""
import shutil
import subprocess
import unittest
from pathlib import Path

SITE = Path(__file__).resolve().parents[1] / "site" / "bench"


class RemapBrowserTests(unittest.TestCase):
    def test_every_browser_source_parses(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node unavailable")
        for path in sorted(SITE.glob("*.js")):
            with self.subTest(path=path.name):
                result = subprocess.run([node, "--check", str(path)],
                                        capture_output=True, text=True,
                                        timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_label_na_ranking_and_pairwise_comparability(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node unavailable")
        code = r"""
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const read=p=>fs.readFileSync(process.argv[p],'utf8');
const app=read(2).replace(/\bmain\(\);\s*$/,'');
const nodes={};
function node(){
  return {textContent:'',innerHTML:'',className:'',hidden:false,value:'',
    disabled:false, options:[], dataset:{},
    classList:{add(){},remove(){}},addEventListener(){},
    querySelector(){return null;},querySelectorAll(){return [];},
    scrollIntoView(){}};
}
const document={getElementById(id){return nodes[id]||(nodes[id]=node());},
  querySelectorAll(){return [];}};
const sandbox=vm.createContext({document,console,URLSearchParams,
  location:{search:''},history:{replaceState(){}},fetch:async()=>({ok:false}),
  BenchOverview:{notice(){return null;},summary(){return {};},
    coverage(){return '';}},BenchDistribution:{}});
vm.runInContext(read(3),sandbox);  // rankings
vm.runInContext(read(4),sandbox);  // distribution
vm.runInContext(read(5),sandbox);  // views
vm.runInContext(read(6),sandbox);  // subjects
vm.runInContext(app,sandbox);

vm.runInContext(`state.run={id:'fixture',cohort:'real',tools:['iva',
  'micall-remap'],expected_sample_count:3,tool_labels:{
  'micall-remap':'MiCall remap (reference-based)',iva:'IVA'},
  tool_modes:{'micall-remap':{kind:'reference-based',de_novo:false,
    description:'Ordinary frozen MiCall; final MAX sequences scored against '
    +'the reference panel.'}},samples:[
  {alias:'R001',score:{iva:100,'micall-remap':110},
    seconds:{iva:10,'micall-remap':12},diagnostics:{'micall-remap':{
      final_contig_count:null,
      unavailable_reasons:{final_contig_count:'not applicable'}},iva:{}},
    failures:[]},
  {alias:'R002',score:{iva:90,'micall-remap':null},
    seconds:{iva:11,'micall-remap':null},diagnostics:{'micall-remap':{}},
    failures:['micall-remap']},
  {alias:'R003',score:{iva:80,'micall-remap':95},
    seconds:{iva:12,'micall-remap':13},diagnostics:{'micall-remap':{}},
    failures:[]}]};`,sandbox);

// The published label and method type travel with the tool everywhere.
const label=vm.runInContext('toolLabelHtml("micall-remap")',sandbox);
assert(label.includes('MiCall remap (reference-based)'),label);
assert(label.includes('reference-based'),label);
assert(label.includes('not de novo'),label);
assert(vm.runInContext('toolLabel("micall-remap")',sandbox)
  ==='MiCall remap (reference-based)');

// Missing is N/A, distinct from a real zero.
assert.equal(vm.runInContext('na(null)',sandbox),'N/A');
assert.equal(vm.runInContext('na(NaN)',sandbox),'N/A');
assert.equal(vm.runInContext('na(0)',sandbox),'0');

// Ranking includes the diagnostic arm only where a measurement exists.
const summary=vm.runInContext('BenchRanks.summary(state.run,null,"score","higher")',
  sandbox);
const remap=summary.find(x=>x.tool==='micall-remap');
assert(remap,'remap absent from ranking');
assert.equal(remap.observed,2);
assert(Math.abs(remap.mean-102.5)<1e-9);

// A failed arm is unavailable in the signed pairwise table, never zero.
const pairs=vm.runInContext('BenchRanks.pairs(state.run,null,"score","higher",'
  +'"iva","micall-remap")',sandbox);
const failed=pairs.find(x=>x.id==='R002');
assert.equal(failed.rival,null);
assert.equal(failed.delta,null);
assert.equal(failed.unavailable,true);

// Per-case detail uses the published label and shows N/A, not 0.
const table=vm.runInContext('BenchViews.sampleTable(state.run,null,"R001",'
  +'"iva","micall-remap")',sandbox);
assert(table.includes('MiCall remap (reference-based)'),table);
assert(table.includes('N/A means unavailable'),table);
assert(table.includes('N/A'),table);

// Method explanation and matrix headers name the type.
const notes=vm.runInContext('methodNotes()',sandbox);
assert(notes.includes('reference-based'),notes);
const subjectsNode=document.getElementById('dominanceSubjects');
subjectsNode.querySelectorAll=()=>[{value:'alignment',checked:true,
  closest(){return {querySelector(){return null;}};}}];
subjectsNode.querySelector=()=>null;
vm.runInContext(`state.run.dominance_matrix={tools:state.run.tools,metrics:{}};
  state.psiExponent='all';state.metric='score';`,sandbox);
vm.runInContext('drawDominance();',sandbox);
const matrix=nodes.dominanceMatrix.innerHTML;
assert(matrix.includes('MiCall remap (reference-based)'),matrix);
assert(matrix.includes('method-badge'),matrix);
console.log('REMAP_DISPLAY_CONTRACT_OK');
"""
        result = subprocess.run(
            [node, "-e", code, SITE.name, str(SITE / "app.js"),
             str(SITE / "rankings.js"), str(SITE / "distribution.js"),
             str(SITE / "compare_views.js"), str(SITE / "subjects.js")],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("REMAP_DISPLAY_CONTRACT_OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
