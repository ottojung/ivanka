"""Seven assembler branch and image contracts require independent evidence."""
import unittest
from unittest.mock import patch

from assembler_bench import dedicated_image_attestation as audit
from expanded.adapters import ASSEMBLERS, PROGRAMS


class DedicatedImageTests(unittest.TestCase):
    @staticmethod
    def fixture():
        baseline="a"*40
        base_id="b"*64
        sources={}
        images={}
        inspected={
            base_id:{
                "Id":base_id,
                "Config":{"Labels":{
                    "org.opencontainers.image.source":audit.SOURCE_REPO,
                    "org.opencontainers.image.revision":baseline}},
                "RootFS":{"Layers":["layer-0","layer-1"]}}}
        for i,name in enumerate(ASSEMBLERS):
            commit=(format(i+1,"x")*40)
            image_id=(format(i+1,"x")*64)
            sources[name]={
                "commit":commit,"source_hashes":{"denovo.py":"f"*64},
                "dockerfile_sha256":"e"*64,
                "base_dockerfile_sha256":"d"*64}
            images[name]=image_id
            inspected[image_id]={
                "Id":image_id,
                "Config":{
                    "Labels":{
                        "org.opencontainers.image.source":audit.SOURCE_REPO,
                        "org.opencontainers.image.revision":commit,
                        "org.ottojung.micall.source-branch":"bench/assembler-"+name,
                        "org.ottojung.micall.assembler":name,
                        "org.ottojung.micall.common-base":base_id,
                        "org.ottojung.micall.common-baseline-commit":baseline},
                    "Env":["MICALL_DENOVO_ASSEMBLER="+name]},
                "RootFS":{"Layers":["layer-0","layer-1","layer-"+name]}}
        return baseline,base_id,sources,images,inspected

    @staticmethod
    def probe(image,names,base_id,images):
        if image==base_id:
            return {"programs":{"iva":"f"*64},
                    "files":{"denovo.py":"f"*64}, "ivanka_elf":False}
        inv={v:k for k,v in images.items()}
        name=inv[image]
        programs={k:"f"*64 for k in set(PROGRAMS[name])|set(PROGRAMS["iva"])}
        return {"programs":programs,"files":{"denovo.py":"f"*64},
                "ivanka_elf":name=="ivanka"}

    def verify_fixture(self,mutate=None):
        baseline,base_id,sources,images,inspected=self.fixture()
        if mutate:
            mutate(baseline,base_id,sources,images,inspected)
        probe=lambda image,names:self.probe(image,names,base_id,images)
        with patch.object(audit,"_source",side_effect=lambda name,root,base:
                    sources[name]),patch.object(audit,"inspect",
                    side_effect=inspected.__getitem__),patch.object(
                    audit,"_program_probe",side_effect=probe):
            return audit.verify(images,{name:"/dummy/"+name
                                       for name in ASSEMBLERS},base_id)

    def test_all_seven_unique_branch_commits_and_images_pass(self):
        result=self.verify_fixture()
        self.assertEqual(result["status"],
                         "SEVEN_INDEPENDENT_BRANCH_IMAGES_VERIFIED")
        self.assertEqual(len(result["images"]),7)
        self.assertEqual(len({v["image_sha256"] for v in
                              result["images"].values()}),7)
        self.assertEqual(len({v["source_commit"] for v in
                              result["images"].values()}),7)
        for name in ASSEMBLERS:
            item=result["images"][name]
            self.assertEqual(item["source_branch"],"bench/assembler-"+name)
            self.assertEqual(item["baseline_commit"],"a"*40)
            self.assertEqual(item["source_url"],
                "https://github.com/ottojung/MiCall/tree/"+item["source_commit"])
            self.assertEqual(set(item["executables_sha256"]),
                             set(PROGRAMS[name])|set(PROGRAMS["iva"]))

    def test_reuse_of_one_container_for_several_tools_is_rejected(self):
        def mutate(base,base_id,sources,images,inspected):
            images["megahit"]=images["ivanka"]
        with self.assertRaisesRegex(ValueError,"same image"):
            self.verify_fixture(mutate)

    def test_shared_source_revision_is_rejected(self):
        def mutate(base,base_id,sources,images,inspected):
            sources["megahit"]["commit"]=sources["ivanka"]["commit"]
        with self.assertRaisesRegex(ValueError,"share one commit"):
            self.verify_fixture(mutate)

    def test_wrong_dedicated_branch_and_wrong_baseline_are_rejected(self):
        for key,value in (
                ("org.ottojung.micall.source-branch","bench/assembler-iva"),
                ("org.ottojung.micall.common-baseline-commit","c"*40),
                ("org.opencontainers.image.source","https://github.com/cfe-lab/MiCall")):
            def mutate(base,base_id,sources,images,inspected,
                       key=key,value=value):
                inspected[images["spades"]]["Config"]["Labels"][key]=value
            with self.subTest(key=key), self.assertRaisesRegex(
                    ValueError,"labels mismatch"):
                self.verify_fixture(mutate)

    def test_extra_contender_binary_rejected_even_if_own_exists(self):
        _baseline,base_id,sources,images,inspected=self.fixture()
        probe=lambda image,names:self.probe(image,names,base_id,images)
        def extra(image,names):
            result=probe(image,names)
            if image==images["spades"]:
                result["programs"]["megahit"]="e"*64
            return result
        with patch.object(audit,"_source",side_effect=lambda name,root,base:
                    sources[name]),patch.object(audit,"inspect",
                    side_effect=inspected.__getitem__),patch.object(
                    audit,"_program_probe",side_effect=extra):
            with self.assertRaisesRegex(ValueError,"extraneous"):
                audit.verify(images,{n:"/dummy/"+n for n in ASSEMBLERS},
                             base_id)

    def test_removed_rust_elf_is_rejected(self):
        _baseline,base_id,sources,images,inspected=self.fixture()
        probe=lambda image,names:self.probe(image,names,base_id,images)
        def missing(image,names):
            result=probe(image,names)
            if image==images["ivanka"]:
                result["ivanka_elf"]=False
            return result
        with patch.object(audit,"_source",side_effect=lambda name,root,base:
                    sources[name]),patch.object(audit,"inspect",
                    side_effect=inspected.__getitem__),patch.object(
                    audit,"_program_probe",side_effect=missing):
            with self.assertRaisesRegex(ValueError,"native Ivanka ELF"):
                audit.verify(images,{n:"/dummy/"+n for n in ASSEMBLERS},
                             base_id)


if __name__=="__main__":
    unittest.main()
