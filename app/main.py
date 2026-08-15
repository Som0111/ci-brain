from fastapi import FastAPI

from app.api import clusters, flakiness, impact, repos, runs

app = FastAPI(title="CI Brain", version="0.1.0")

app.include_router(repos.router)
app.include_router(runs.router)
app.include_router(flakiness.router)
app.include_router(impact.router)
app.include_router(clusters.router)


@app.get("/health")
def health():
    return {"status": "ok"}
