import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import benchmark, clusters, flakiness, impact, repos, runs
from app.config import settings
from app.logging_config import configure_logging, want_traceback

configure_logging()
logger = logging.getLogger(__name__)
app = FastAPI(title="CI Brain", version="0.1.0")


# Error shape: always {"detail": ...}. HTTPException -> string; 422 -> list of {loc, msg}
# (pydantic's "input"/"ctx" are dropped so uploaded/user data is never echoed back);
# anything unhandled -> generic 500 with no internals.
@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError):
    errors = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(Exception)
async def _unhandled_error(request: Request, exc: Exception):
    logger.error(
        "unhandled %s on %s %s", type(exc).__name__, request.method, request.url.path, exc_info=want_traceback()
    )
    return JSONResponse(status_code=500, content={"detail": "internal server error"})

# Dashboard runs on its own dev-server origin (and may be hosted separately
# from the API in production), so it needs cross-origin access. Origins come from
# CORS_ORIGINS (default "*"). CORS is not authentication - writes/LLM calls are
# protected separately by the optional API_KEY (see app/security.py).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()] or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],
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
