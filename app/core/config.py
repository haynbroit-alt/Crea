from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "AI Video Agent"
    app_version: str = "1.0.0"
    debug: bool = False
    output_dir: str = "output"
    anthropic_api_key: str | None = None
    claude_model: str = "claude-haiku-4-5-20251001"

    class Config:
        env_file = ".env"


settings = Settings()
