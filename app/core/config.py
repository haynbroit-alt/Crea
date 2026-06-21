from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "AI Video Agent"
    app_version: str = "1.0.0"
    debug: bool = False
    output_dir: str = "output"

    class Config:
        env_file = ".env"


settings = Settings()
