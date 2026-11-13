"""Public source links and independent one-image-per-tool evidence."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from assembler_bench.dedicated_publication import check
from assembler_bench.site_build import SITE, build, validate_public_site
from expanded.adapters import ASSEMBLERS


FIXTURE=Path(__file__).resolve().parent/"fixtures/assembler_bench_dedicated"


class DedicatedPublicationTests(unittest.TestCase):
    def test_all_seven_verified_branch_links_and_images_are_published(self):
        self.assertEqual(check(FIXTURE),len(ASSEMBLERS))
        data=json.loads((FIXTURE/"data/dedicated-images.json").read_text())
        self.assertEqual(data["schema"],
                         "ivanka.assembler-bench.dedicated-fork-images.v1")
        self.assertEqual(data["status"],
                         "SEVEN_INDEPENDENT_BRANCH_IMAGES_VERIFIED")
        self.assertEqual(len({v["image_sha256"] for v in
                              data["images"].values()}),7)
        self.assertEqual(len({v["source_commit"] for v in
                              data["images"].values()}),7)
        for name,source in data["images"].items():
            self.assertEqual(source["source_branch"],
                             "bench/assembler-"+name)
            self.assertEqual(source["source_url"],
                "https://github.com/ottojung/MiCall/tree/"+
                source["source_commit"])
            self.assertEqual(source["baseline_url"],data["baseline_url"])
        js=(SITE/"app.js").read_text()
        self.assertNotIn('fetch("./data/dedicated-images.json"',js)
        self.assertIn('source_url',js)
        self.assertIn('source_commit',js)
        self.assertIn('Assembler builds',js)
        self.assertIn('esc(item.image_sha256)',js)
        self.assertNotIn('item.image_sha256.slice(',js)
        self.assertIn('provenance-scroll',js)
        published = json.loads((SITE / "data/runs.json").read_text())
        self.assertEqual(validate_public_site(), len(published["runs"]))

    def test_forged_fork_links_reused_images_and_status_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/"site"
            shutil.copytree(FIXTURE,root)
            file=root/"data/dedicated-images.json"
            original=json.loads(file.read_text())
            changes=(
                lambda d: d["images"]["spades"].update(
                    source_url="https://github.com/cfe-lab/MiCall"),
                lambda d: d["images"]["velvet"].update(
                    image_sha256=d["images"]["iva"]["image_sha256"]),
                lambda d: d.update(status="PASSED_FULL_BENCHMARK"),
                lambda d: d["images"]["megahit"].update(
                    source_branch="bench/assembler-iva"),
            )
            for mutator in changes:
                data=json.loads(json.dumps(original))
                mutator(data)
                file.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    check(root)

    def test_pages_artifact_contains_only_current_source_attestation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"_site"
            build(root)
            self.assertFalse(
                (root/"bench/data/dedicated-images.json").exists())
            self.assertTrue(
                (root/"bench/data/live-fork-attestation.json").is_file())


if __name__=="__main__":
    unittest.main()
