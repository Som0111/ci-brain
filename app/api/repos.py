from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Repo
from app.schemas import RepoCreate, RepoOut

router = APIRouter(prefix="/repos", tags=["repos"])


@router.post("", response_model=RepoOut, status_code=201)
def create_repo(payload: RepoCreate, db: Session = Depends(get_db)):
    existing = db.scalar(select(Repo).where(Repo.name == payload.name))
    if existing:
        raise HTTPException(status_code=409, detail=f"repo '{payload.name}' already exists")

    repo = Repo(name=payload.name, url=payload.url)
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return repo


@router.get("", response_model=list[RepoOut])
def list_repos(db: Session = Depends(get_db)):
    return db.scalars(select(Repo).order_by(Repo.id)).all()


@router.get("/{repo_id}", response_model=RepoOut)
def get_repo(repo_id: int, db: Session = Depends(get_db)):
    repo = db.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="repo not found")
    return repo
