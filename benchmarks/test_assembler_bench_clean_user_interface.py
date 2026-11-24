"""A compact, user-oriented site with one complete build provenance table."""
import shutil
import subprocess
import unittest

from assembler_bench.site_build import SITE


class CleanWebsiteTests(unittest.TestCase):
    def test_page_has_no_redundant_panels_or_decorative_title_period(self):
        html = (SITE/"index.html").read_text()
        js = (SITE/"app.js").read_text()
        self.assertIn("<em>Bench</em>", html)
        self.assertNotIn("<em>Bench.</em>", html)
        self.assertNotIn("PUBLIC RESULTS · SOURCE-ATTESTED", html)
        for removed in ("diagnosticMatrix", "diagnosticChart",
                        "diagnosticContext", "evidenceContent",
                        'class="evidence"', 'coverage-section'):
            self.assertNotIn(removed, html)
        self.assertNotIn("drawEvidence()", js)
        self.assertNotIn("drawEvidence()", html)
        self.assertNotIn("drawEvidence();", js)
        self.assertNotIn("Unmeasured diagnostics cannot be scored as zero", js)
        self.assertNotIn("Failures are not wins", js)
        self.assertNotIn("Only fully measured cases are checked", js)
        self.assertNotIn("different original score scales", js)

    def test_js_renders_each_cohort_assembler_and_full_image_hashes_once(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node unavailable")
        code = r"""
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const js=fs.readFileSync(process.argv[1],'utf8');
const runs=JSON.parse(fs.readFileSync(process.argv[2],'utf8')).runs;
const result={innerHTML:''};
const context={document:{getElementById:id=>{
  assert.equal(id,'provenanceContent');return result;
}},BenchRanks:{},BenchSubjects:{},console};
const sandbox=vm.createContext(context);
vm.runInContext(js.replace(/\bmain\(\);\s*$/,''),sandbox);
for(const run of runs){
 sandbox.TEST_RUN=run;
 vm.runInContext('state.run=TEST_RUN;drawProvenance();',sandbox);
 const html=result.innerHTML;
 assert(html.includes('class="table-scroll provenance-scroll"'));
 assert(html.includes('<h3>Assembler builds</h3>'));
 const rows=(html.match(/<tr><th scope="row">/g)||[]).length;
 assert.equal(rows,run.tools.length,run.cohort);
 for(const tool of run.tools){
  const label=vm.runInContext('toolLabel('+JSON.stringify(tool)+')',sandbox);
  assert(html.includes('<th scope="row">'+label+'</th>'),tool);
  const image=run.micall_fork_provenance.images[tool];
  const provenance=run.roster.find(row=>row.id===tool)?.provenance||{};
  const digest=image?.image_sha256||provenance.image_sha256||run.images[tool];
  const commit=image?.source_commit||provenance.adapter_commit;
  if(digest)assert.equal(html.split(digest).length-1,1,tool);
  if(commit)assert(html.includes(commit),tool);
  const branch=image?.source_branch||provenance.source_branch;
  assert(branch,tool+" missing branch");
  assert(html.includes("<td>"+branch+"</td>"),tool+" branch not rendered");
  if(!digest)assert(html.includes('Not recorded'),tool);
 }
 // A cohort with a different roster must never show out-of-cohort builds.
 sandbox.TEST_RUN={...run,tools:[run.tools.at(-1)]};
 vm.runInContext('state.run=TEST_RUN;drawProvenance();',sandbox);
 assert.equal((result.innerHTML.match(/<tr><th scope="row">/g)||[]).length,1);
}
console.log('COMPLETE_SINGLE_IMAGE_TABLE_OK');
"""
        process = subprocess.run(
            [node, "-e", code, str(SITE/"app.js"),
             str(SITE/"data/runs.json")],
            capture_output=True, text=True, timeout=15)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("COMPLETE_SINGLE_IMAGE_TABLE_OK", process.stdout)


if __name__ == "__main__":
    unittest.main()
