from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://ci_brain:ci_brain@localhost:5432/ci_brain"
    gemini_api_key: str | None = None

    model_config = {"env_file": ".env"}


settings = Settings()
