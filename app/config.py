"""Validated application settings loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    groq_api_key: str = ""
    groq_model: str = ""
    max_tasks: int = Field(default=8, ge=4, le=20)
    max_retries: int = Field(default=1, ge=0, le=3)
    max_request_length: int = Field(default=10_000, ge=100, le=50_000)
    generated_documents_dir: Path = Path("generated_documents")
    max_document_size_bytes: int = Field(default=10_000_000, ge=1024)
    min_document_characters: int = Field(default=300, ge=50)
    llm_timeout_seconds: float = Field(default=60, gt=0, le=300)
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("generated_documents_dir", mode="before")
    @classmethod
    def normalize_documents_directory(cls, value: object) -> Path:
        return Path(value).expanduser()

    def require_groq_credentials(self) -> tuple[str, str]:
        if not self.groq_api_key.strip():
            raise ValueError("GROQ_API_KEY is required. Add it to the project's .env file.")
        if not self.groq_model.strip():
            raise ValueError("GROQ_MODEL is required. Set a model available to your Groq account.")
        return self.groq_api_key.strip(), self.groq_model.strip()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        raise ValueError("Application configuration is invalid; review the documented environment settings.") from exc
