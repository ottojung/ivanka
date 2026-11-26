import unittest
from datetime import datetime, timedelta

from px_stage_interval_diagnostic import MARKERS, ORDER, intervals

MESSAGES = {
    "startup": "Starting on container with 32 CPUs.",
    "sample_setup": "Processing Sample X.",
    "merge_entropy": "Running merge_for_entropy on Sample X.",
    "fastq_g2p": "Running fastq_g2p on Sample X.",
    "native_assembly": "Running de novo assembly on Sample X.",
    "assembly_tail": "Assembled 3 contigs in 0:00:01.000",
    "remap": "Running remap on Sample X.",
    "sam2aln": "Running sam2aln on Sample X.",
    "aln2counts": "Running aln2counts on Sample X.",
    "coverage_plots": "Running coverage_plots on Sample X.",
    "cascade_report": "Running cascade_report on Sample X.",
    "sample_tail": "Finished sample Sample X.",
    "resistance": "Running resistance on Sample X.",
    "resistance_report": "Running resistance report on Sample X.",
    "run_tail": "Finished resistance of Sample X.",
    "done": "Done.",
}


def log(order=ORDER, times=None):
    base = datetime(2026, 1, 1)
    if times is None:
        times = range(len(order))
    return "\n".join(
        (base + timedelta(seconds=t)).strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
        + "[INFO]micall.example(): " + MESSAGES[name]
        for name, t in zip(order, times)
    )


class IntervalsTest(unittest.TestCase):
    def test_stage_sum_and_repeated_passes(self):
        self.assertEqual(set(MESSAGES), {name for name, _ in MARKERS})
        a = intervals(log(), 22)
        self.assertEqual(a["logged_span_seconds"], len(ORDER) - 1)
        self.assertEqual(a["official_minus_logged_span_seconds"], 22 - len(ORDER) + 1)
        self.assertEqual(a["stage_intervals_seconds"]["sam2aln"], 2)
        self.assertEqual(a["stage_intervals_seconds"]["native_assembly"], 1)

    def test_missing_or_extra_marker(self):
        for order in (ORDER[:-1], ORDER + ["done"], ORDER[:6] + ORDER[7:]):
            with self.subTest(order=order), self.assertRaisesRegex(ValueError, "stage_order"):
                intervals(log(order), 20)

    def test_nonmonotonic(self):
        t = list(range(len(ORDER)))
        t[7] = 1
        with self.assertRaisesRegex(ValueError, "nonmonotonic"):
            intervals(log(times=t), 20)

    def test_signed_gap(self):
        self.assertEqual(intervals(log(), 1)["official_minus_logged_span_seconds"],
                         2 - len(ORDER))
