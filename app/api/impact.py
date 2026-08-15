from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.analysis.impact import (
    build_dependency_graph,
    get_all_tests,
    get_tests_by_file,
    select_tests,
)
from app.database import get_db
from app.models import Repo

router = APIRouter(tags=["impact"])


class ImpactRequest(BaseModel):
    changed_files: list[str]


class ImpactResponse(BaseModel):
    repo_id: int
    changed_files: list[str]
    total_tests: int
    selected_count: int
    reduction_pct: float
    full_suite_fallback: bool
    reasons: list[str]
    unknown_files: list[str]
    selected_tests: list[str]


@router.post("/repos/{repo_id}/impact", response_model=ImpactResponse)
def analyze_impact(repo_id: int, payload: ImpactRequest, db: Session = Depends(get_db)):
    if db.get(Repo, repo_id) is None:
        raise HTTPException(status_code=404, detail="repo not found")

    graph = build_dependency_graph(db, repo_id)
    all_tests = get_all_tests(db, repo_id)
    tests_by_file = get_tests_by_file(db, repo_id)

    result = select_tests(payload.changed_files, graph, all_tests, tests_by_file)

    total = len(all_tests)
    reduction = (1 - result.selected_count / total) * 100 if total else 0.0

    return ImpactResponse(
        repo_id=repo_id,
        changed_files=payload.changed_files,
        total_tests=total,
        selected_count=result.selected_count,
        reduction_pct=round(reduction, 2),
        full_suite_fallback=result.full_suite_fallback,
        reasons=result.reasons,
        unknown_files=result.unknown_files,
        selected_tests=sorted(result.selected),
    )


class GraphSummary(BaseModel):
    repo_id: int
    files: int
    edges: int
    file_test_counts: dict[str, int]


@router.get("/repos/{repo_id}/impact/graph", response_model=GraphSummary)
def graph_summary(repo_id: int, db: Session = Depends(get_db)):
    if db.get(Repo, repo_id) is None:
        raise HTTPException(status_code=404, detail="repo not found")

    graph = build_dependency_graph(db, repo_id)
    return GraphSummary(
        repo_id=repo_id,
        files=len(graph),
        edges=sum(len(v) for v in graph.values()),
        file_test_counts={k: len(v) for k, v in sorted(graph.items())},
    )
