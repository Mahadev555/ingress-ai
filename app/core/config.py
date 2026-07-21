from pydantic import BaseSettings

class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379/0"
    postgres_url: str = "postgresql+asyncpg://localhost/ingress_ai"
    openai_api_url: str = "https://api.openai.com/v1"

    class Config:
        env_file = ".env"

settings = Settings()
