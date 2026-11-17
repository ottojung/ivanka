"""Authenticate resource recovery with original score/panel and 50m time."""
from pathlib import Path

from benchmarks.expanded.comparators_first_real import PANEL
from benchmarks.expanded.comparators_first_real import verify as original_verify
from .arm import authenticate


def verify(record, row, tool, image, panel, pmm):
    if record.get("failed") is True:
        return original_verify(record, row, tool, image, panel, pmm)
    if (record.get("sample") != row["sample"]
            or record.get("input_sha256") != row["input_sha256"]
            or record.get("tool") != tool or record.get("image_id") != image
            or record.get("reference_panel_sha256") != PANEL
            or record.get("status") != "finished"
            or record.get("failed") is not False):
        raise ValueError("resource retry identity mismatch")
    arm = record.get("arm")
    authenticate(arm, image, Path(pmm.RESULTS))
    measure = record.get("measurement")
    if not isinstance(measure, dict):
        raise ValueError("missing extended MiCall measurement")
    score = pmm.best_panel_alignment(
        pmm.final_max_sequences(arm["artifact_dir"]), panel)["score"]
    if (measure.get("seconds") != arm["seconds"]
            or type(measure.get("score")) not in (int, float)
            or measure["score"] != float(score)):
        raise ValueError("extended MiCall alignment score differs")
    return record
