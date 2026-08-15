from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import benchmark, clusters, flakiness, impact, repos, runs

app = FastAPI(title="CI Brain", version="0.1.0")

# Dashboard runs on its own dev-server origin (and may be hosted separately
# from the API in production), so it needs cross-origin access. No auth on
# this API yet (documented limitation), so this is intentionally permissive -
# fine for a local/portfolio project, would need real origin restriction
# before this API held anything sensitive.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(repos.router)
app.include_router(runs.router)
app.include_router(flakiness.router)
app.include_router(impact.router)
app.include_router(clusters.router)
app.include_router(benchmark.router)


@app.get("/health")
def health():
    return {"status": "ok"}
