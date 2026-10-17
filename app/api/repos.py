from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Repo
from app.schemas import RepoCreate, RepoOut
from app.security import require_api_key

router = APIRouter(prefix="/repos", tags=["repos"])


@router.post(
    "",
    response_model=RepoOut,
    status_code=201,
    dependencies=[Depends(require_api_key)],
    responses={
        401: {"description": "Missing or invalid X-API-Key (only when API_KEY is configured)"},
        409: {"description": "A repo with this name already exists"},
    },
)
def create_repo(payload: RepoCreate, db: Session = Depends(get_db)):
    existing = db.scalar(select(Repo).where(Repo.name == payload.name))
    if existing:
        raise HTTPException(status_code=409, detail=f"repo '{payload.name}' already exists")

    repo = Repo(name=payload.name, url=payload.url)
    db.add(repo)
    try:
        db.commit()
    except IntegrityError as exc:  # lost a race with a concurrent create of the same name
        db.rollback()
        raise HTTPException(status_code=409, detail=f"repo '{payload.name}' already exists") from exc
    db.refresh(repo)
    return repo


@router.get("", response_model=list[RepoOut])
def list_repos(db: Session = Depends(get_db)):
    return db.scalars(select(Repo).order_by(Repo.id)).all()


@router.get("/{repo_id}", response_model=RepoOut, responses={404: {"description": "Repo not found"}})
def get_repo(repo_id: int, db: Session = Depends(get_db)):
    repo = db.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="repo not found")
    return repo
