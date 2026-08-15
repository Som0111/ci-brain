"""Serves Phase 4's real, measured test-impact-analysis benchmark results.

This is a committed snapshot (`app/data/benchmark_results.json`), not a
live-recomputed number - the actual benchmark methodology (interleaved A/B
sampling, multiple reps, a quiet machine) takes minutes and isn't something
to redo on every dashboard page load. The numbers are real measurements
(see HUMAN_GUIDE.md's Phase 4 section for the full methodology and the two
measurement bugs found and fixed while producing them), just not
recalculated per-request.
"""
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["benchmark"])

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "benchmark_results.json"


@router.get("/benchmark")
def get_benchmark():
    if not _DATA_PATH.exists():
        raise HTTPException(status_code=404, detail="no benchmark results recorded yet")
    return json.loads(_DATA_PATH.read_text(encoding="utf-8"))
