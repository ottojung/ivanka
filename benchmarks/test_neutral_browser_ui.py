"""Frontend-only regression tests for the assembler-neutral browser.

The public site reports measured evidence and provenance. It must not carry
project-acceptance vocabulary, a separate experimental roster panel, or a
hard-coded assembler count, and every comparison control must follow the
roster published by the selected run.
"""
import re
import shutil
import subprocess
import unittest
from pathlib import Path

SITE = Path(__file__).resolve().parents[1] / "site" / "bench"
PUBLIC_BROWSER_SUFFIXES = (".html", ".js", ".css")
FORBIDDEN = re.compile(r"qualif|ineligib|\bgates?\b", re.IGNORECASE)
# Release thresholds and approval verdicts are not part of a measurement UI.
NON_NEUTRAL = re.compile(
    r"90 ?%|floor_ok|\brelease\b|\bapprov(al|ed)?\b|\bpass(ed|ing)?\b|"
    r"baseline_assemblers",
    re.IGNORECASE)


def public_browser_sources():
    return sorted(p for p in SITE.rglob("*")
                  if p.is_file() and p.suffix in PUBLIC_BROWSER_SUFFIXES)


class NeutralBrowserTests(unittest.TestCase):
    def test_no_acceptance_vocabulary_in_public_browser_sources(self):
        sources = public_browser_sources()
        self.assertTrue(sources)
        for path in sources:
            with self.subTest(path=path.relative_to(SITE)):
                text = path.read_text()
                match = FORBIDDEN.search(text) or NON_NEUTRAL.search(text)
                self.assertIsNone(
                    match,
                    f"{path.name} contains non-neutral vocabulary: "
                    f"{match.group(0)!r}" if match else "")

    def test_no_separate_experimental_roster_or_hardcoded_count(self):
        html = (SITE / "index.html").read_text()
        js = (SITE / "app.js").read_text()
        css = (SITE / "style.css").read_text()
        self.assertNotIn("exploratory.js", html)
        self.assertNotIn("exploratory-candidates.json", js)
        self.assertNotIn('class="exploratory"', html)
        self.assertNotIn("BenchExploratory", js)
        self.assertNotIn("section.exploratory", css)
        self.assertNotIn(".px-compare", css)
        for phrase in ("seven genome assemblers", "Ten nonqualifying",
                       "seven-way", "QUALIFICATION"):
            self.assertNotIn(phrase, html)
        self.assertIn('id="rosterNote"', html)
        self.assertIn("run.tools.length", js)

    def test_every_javascript_file_parses(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node unavailable")
        for path in sorted(SITE.glob("*.js")):
            with self.subTest(path=path.name):
                result = subprocess.run(
                    [node, "--check", str(path)],
                    capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_controls_matrix_and_labels_follow_selected_run_roster(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node unavailable")
        code = r"""
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const subjectJs=fs.readFileSync(process.argv[1],'utf8');
const appJs=fs.readFileSync(process.argv[2],'utf8')
  .replace(/\bmain\(\);\s*$/,'');
const nodes={};
function node(){
  return {textContent:'',innerHTML:'',className:'',hidden:false,value:'',
    disabled:false, options:[], dataset:{},
    classList:{add(){},remove(){}},
    addEventListener(){}, querySelector(){return null;},
    querySelectorAll(){return [];}, scrollIntoView(){}};
}
const document={getElementById(id){return nodes[id]||(nodes[id]=node());},
  querySelectorAll(){return [];}};
const sandbox=vm.createContext({document,console,
  URLSearchParams,location:{search:''},history:{replaceState(){}},
  fetch:async()=>({ok:false}),BenchRanks:{},BenchViews:{},
  BenchOverview:{notice(){return null;},summary(){return {};},
    coverage(){return '';}},BenchDistribution:{}});
vm.runInContext(subjectJs,sandbox);
vm.runInContext(appJs,sandbox);

// Opaque new tools are shown from the roster, never from a fixed seven.
vm.runInContext(`state.run={tools:['skesa','minia','abyss'],
  tool_labels:{skesa:'SKESA'}};`,sandbox);
assert.equal(vm.runInContext('toolLabel("skesa")',sandbox),'SKESA');
assert.equal(vm.runInContext('toolLabel("minia")',sandbox),'Minia');
assert.equal(vm.runInContext('toolLabel("abyss")',sandbox),'ABySS');

// Coverage is an observed count, not an approval verdict.
vm.runInContext(`state.run={tools:['a','b'],expected_sample_count:10,
  tool_progress:{a:{expected:10,finished:8,failed:2},
    b:{expected:10,finished:10,failed:0}}};`,sandbox);
const cov=vm.runInContext('coverageStatus(state.run)',sandbox);
assert.equal(cov.text,'18/20 measured · 2 failed');
assert.equal(cov.cls,'status-partial');

// The matrix axes and pair selectors come solely from run.tools. Missing
// tools in the published matrix still appear with honest unavailable cells.
vm.runInContext(`state.run={id:'r',cohort:'combined',tools:['skesa','minia',
  'abyss'],samples:[],dominance_matrix:{metrics:{}}};
  state.psiExponent='all';state.metric='score';`,sandbox);
const subjectsNode=document.getElementById('dominanceSubjects');
subjectsNode.querySelectorAll=()=>[{value:'alignment',checked:true,
  closest(){return {querySelector(){return null;}};}}];
subjectsNode.querySelector=()=>null;
vm.runInContext('drawDominance();',sandbox);
const html=nodes.dominanceMatrix.innerHTML;
assert(html.includes('<table class="psi-matrix">'));
for(const tool of ['skesa','minia','abyss']){
  assert(html.includes(tool),tool+' absent from matrix');
}
assert.equal((html.match(/dom-self/g)||[]).length,3);
console.log('NEUTRAL_BROWSER_ROSTER_OK');
"""
        result = subprocess.run(
            [node, "-e", code, str(SITE / "subjects.js"), str(SITE / "app.js")],
            capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("NEUTRAL_BROWSER_ROSTER_OK", result.stdout)


    def test_no_release_threshold_control_or_ivanka_identity(self):
        html = (SITE / "index.html").read_text()
        js = (SITE / "app.js").read_text()
        self.assertNotIn('value="floor"', html)
        self.assertNotIn("90%", html)
        self.assertNotIn("floor_ok", js)
        self.assertNotIn("90%", js)
        # The browser accepts publisher-owned schema namespaces without
        # hard-coding a hosting project's identity.
        self.assertNotIn("ivanka.assembler-bench", js)
        self.assertIn("assembler-bench\\.public\\.v1", js)
        self.assertIn("assembler-bench\\.execution-history\\.v1", js)
        for name in ("app.js", "overview.js", "compare_views.js"):
            with self.subTest(name=name):
                self.assertNotIn("ivanka", (SITE / name).read_text().lower())

    def test_sample_dialog_shows_observed_alignment_and_provenance(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node unavailable")
        code = r"""
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const appJs=fs.readFileSync(process.argv[1],'utf8')
  .replace(/\bmain\(\);\s*$/,'');
const nodes={};
function node(){
  return {textContent:'',innerHTML:'',className:'',hidden:false,value:'',
    open:false,showModal(){},classList:{add(){},remove(){}},
    addEventListener(){},querySelector(){return null;},
    querySelectorAll(){return [];}};
}
const document={getElementById(id){return nodes[id]||(nodes[id]=node());},
  querySelectorAll(){return [];}};
const sandbox=vm.createContext({document,console,
  BenchOverview:{},BenchDistribution:{},BenchViews:{sampleTable:()=>'<p>metrics</p>'},
  BenchRanks:{
    definition:()=>({unit:'alignment points'}),
    measurements:(run,snap,key,tool)=>[{id:'C1',
      value:tool==='a'?123.4:98.2,weight:1}]
  }});
vm.runInContext(appJs,sandbox);
vm.runInContext(`state.run={tools:['a','b']};state.firstTool='a';
  state.tool='b';state.diagnostics=null;`,sandbox);
vm.runInContext(`showDetail({id:'C1',detail:{failures:['b'],family:'F1'}});`,sandbox);
const summary=nodes.sampleDialogSummary.textContent;
assert(summary.includes('Observed final MiCall alignment:'));
assert(summary.includes('123.4 alignment points vs 98.2 alignment points'));
assert(summary.includes('Case: C1'));
assert(summary.includes('Family: F1'));
assert(summary.includes('Failed arms: b'));
assert(!/floor|90%|qualified|not met|release|pass/i.test(summary));
console.log('OBSERVED_ALIGNMENT_ONLY_OK');
"""
        result = subprocess.run(
            [node, "-e", code, str(SITE / "app.js")],
            capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OBSERVED_ALIGNMENT_ONLY_OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
