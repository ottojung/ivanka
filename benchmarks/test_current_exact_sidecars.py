"""V6 public exact-read sidecars are additional metrics, never score changes."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from assembler_bench import current_inputs_v6
from assembler_bench import current_inputs
from benchmarks.expanded.adapters import ASSEMBLERS


class ExactSidecarTests(unittest.TestCase):
    def test_v6_synthetic_attaches_verified_values_without_changing_scores(self):
        with TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / "run_manifest.json").write_text("{}")
            images = {tool: str(i + 1) * 64
                      for i, tool in enumerate(ASSEMBLERS)}
            arm = {
                "status": "success", "score": 8700.0, "seconds": 1.25,
                "final_dominant": {"conseq_csv_sha256": "c" * 64},
                "per_truth": {"truth_0": {"fraction": 0.87}},
            }
            with (patch.object(current_inputs_v6, "attest", return_value={
                    "cases": [{"id": "clonal-s000"}]}),
                  patch.object(current_inputs_v6, "case_sources", return_value={
                      "truth_0": (100, "d" * 64, 1.0)}),
                  patch.object(current_inputs_v6, "verified_arm",
                               side_effect=lambda _path, tool, *_:
                               arm if tool == "iva" else None),
                  patch.object(current_inputs_v6, "synthetic_metrics",
                               return_value={"average_read_depth": 20}),
                  patch.object(current_inputs_v6, "exact_metrics",
                               return_value=(
                                   {"average_read_depth": 20,
                                    "exact_coverage_mean": 12.5},
                                   {"full_span": [12.5]})) as exact):
                rows, _ = current_inputs_v6.synthetic(
                    folder, folder, images, folder, folder,
                    exact_root=folder / "cache")
            entry = rows["clonal-s000"]
            self.assertEqual(entry["score"]["iva"], 8700.0)
            self.assertEqual(entry["seconds"]["iva"], 1.25)
            self.assertEqual(
                entry["diagnostics"]["iva"]["exact_coverage_mean"], 12.5)
            self.assertEqual(
                entry["exact_profiles"]["iva"], {"full_span": [12.5]})
            exact.assert_called_once_with(
                {"average_read_depth": 20}, folder / "cache",
                "synthetic", "clonal-s000", "iva", "c" * 64, images["iva"])

    def test_physical_attaches_only_matching_scoped_provenance(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            data = base / "input"
            data.mkdir()
            original = base / "phase-real198"
            original.mkdir()
            (original / "run_manifest.json").write_text("{}")
            names = [f"sample{i:03d}" for i in range(198)]
            (data / "manifest.tsv").write_text(
                "sample\n" + "\n".join(names) + "\n")
            images = {tool: str(i + 1) * 64
                      for i, tool in enumerate(ASSEMBLERS)}
            run = {
                "expected_samples": 198,
                "reference_panel_sha256": current_inputs.PANEL,
                "source_manifest_sha256": current_inputs.PHYSICAL_MANIFEST,
                "images": {n: v for n, v in images.items() if n != "ivanka"},
            }
            arm = {
                "status": "success", "score": 4200.0, "seconds": 5,
                "conseq_digest": "c" * 64, "metrics": {},
            }
            with (patch.object(current_inputs, "freeze", return_value=run),
                  patch.object(current_inputs, "sha",
                               side_effect=lambda path:
                               current_inputs.PHYSICAL_MANIFEST
                               if Path(path).name == "manifest.tsv"
                               else "0" * 64),
                  patch.object(current_inputs, "physical_pairs",
                               return_value={n: [] for n in names}),
                  patch.object(current_inputs, "real_arm",
                               side_effect=lambda _r, t, n, *_:
                               arm if n == names[0] and t == "iva" else None),
                  patch.object(current_inputs, "physical_metrics",
                               return_value={"average_read_depth": 7}),
                  patch.object(current_inputs, "exact_metrics",
                               return_value=(
                                   {"average_read_depth": 7,
                                    "exact_coverage_mean": 8},
                                   {"inner_70": [8]})) as exact):
                rows, _ = current_inputs.physical(
                    original, data, images, base, base, base, base,
                    exact_root=base / "cache")
            row = rows[names[0]]
            self.assertEqual(row["score"]["iva"], 4200.0)
            self.assertEqual(row["seconds"]["iva"], 5)
            self.assertEqual(row["diagnostics"]["iva"]["exact_coverage_mean"], 8)
            self.assertEqual(row["exact_profiles"]["iva"], {"inner_70": [8]})
            exact.assert_called_once_with(
                {"average_read_depth": 7}, base / "cache",
                "real", names[0], "iva", "c" * 64, images["iva"],
                candidate="iva")


if __name__ == "__main__":
    unittest.main()
