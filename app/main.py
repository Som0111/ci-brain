from fastapi import FastAPI

from app.api import repos, runs

app = FastAPI(title="CI Brain", version="0.1.0")

app.include_router(repos.router)
app.include_router(runs.router)


@app.get("/health")
def health():
    return {"status": "ok"}
