"""Public source links and independent one-image-per-tool evidence."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from assembler_bench.dedicated_publication import check
from assembler_bench.site_build import SITE, build, validate_public_site
from expanded.adapters import ASSEMBLERS


class DedicatedPublicationTests(unittest.TestCase):
    def test_all_seven_verified_branch_links_and_images_are_published(self):
        self.assertEqual(check(SITE),len(ASSEMBLERS))
        data=json.loads((SITE/"data/dedicated-images.json").read_text())
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
        self.assertIn('fetch("./data/dedicated-images.json"',js)
        self.assertIn('source_url',js)
        self.assertIn('source_commit',js)
        self.assertIn('These are available branch-specific builds',js)
        self.assertEqual(validate_public_site(),3)

    def test_forged_fork_links_reused_images_and_status_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/"site"
            shutil.copytree(SITE,root)
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
                    validate_public_site(root)

    def test_pages_artifact_contains_dedicated_source_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"_site"
            build(root)
            file=root/"bench/data/dedicated-images.json"
            self.assertTrue(file.is_file())
            self.assertEqual(check(root/"bench"),7)


if __name__=="__main__":
    unittest.main()
