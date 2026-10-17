from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://ci_brain:ci_brain@localhost:5432/ci_brain"
    gemini_api_key: str | None = None
    log_level: str = "INFO"  # DEBUG also enables tracebacks in error logs
    # Comma-separated browser origins allowed by CORS; "*" = any (fine for the public read-mostly demo).
    cors_origins: str = "*"
    # When set, POST /repos, POST /repos/{id}/runs and the LLM summarize endpoint require header X-API-Key.
    api_key: str | None = None
    max_results_per_run: int = 50_000  # test results stored from one JUnit upload
    gemini_timeout_seconds: float = 15.0
    max_upload_bytes: int = 25_000_000  # per uploaded file (JUnit XML / coverage JSON)

    model_config = {"env_file": ".env"}


settings = Settings()
