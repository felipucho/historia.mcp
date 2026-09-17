"""Configuración por entorno (.env en la raíz). Se valida al importar: config inválida = no arranca."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    backend_host: str = "127.0.0.1"
    backend_port: int = Field(8000, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    data_file: Path = ROOT_DIR / "fundacion.json"
    ia_config_dir: Path = ROOT_DIR / "ia_config"

    ollama_url: HttpUrl = HttpUrl("http://localhost:11434")
    ollama_model: str = Field("llama3.2", min_length=1)
    ollama_num_ctx: int = Field(8192, ge=2048)
    ollama_keep_alive: str = "30m"
    ollama_connect_timeout: float = Field(5.0, gt=0)
    ollama_read_timeout: float = Field(90.0, gt=0, le=300)
    ollama_required: bool = False

    mcp_connect_timeout: float = Field(20.0, gt=0)
    mcp_call_timeout: float = Field(15.0, gt=0)
    mcp_retry_base: float = Field(2.0, gt=0)
    mcp_retry_max: float = Field(60.0, gt=0)

    agent_max_iterations: int = Field(5, ge=1, le=5)
    history_max_turns: int = Field(6, ge=1)

    ws_max_connections_per_ip: int = Field(5, ge=1)
    ws_rate_capacity: int = Field(5, ge=1)
    ws_rate_refill_per_minute: float = Field(10.0, gt=0)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("cors_origins")
    @classmethod
    def _reject_wildcard(cls, value: list[str]) -> list[str]:
        if "*" in value:
            raise ValueError("CORS_ORIGINS no admite '*': listá los orígenes permitidos")
        return value

    @field_validator("data_file", "ia_config_dir")
    @classmethod
    def _resolve_from_root(cls, value: Path) -> Path:
        return value if value.is_absolute() else (ROOT_DIR / value).resolve()

    @property
    def ollama_base_url(self) -> str:
        return str(self.ollama_url).rstrip("/")
