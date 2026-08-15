from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://ci_brain:ci_brain@localhost:5432/ci_brain"

    model_config = {"env_file": ".env"}


settings = Settings()
