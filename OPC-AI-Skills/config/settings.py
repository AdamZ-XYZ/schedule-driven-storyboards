from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    opc_base_url: str = ""
    opc_token_url: str = ""
    opc_client_id: str = ""
    opc_client_secret: str = ""
    opc_project_id: str = ""

    session_grace_minutes: int = 10
    cache_backend: str = "memory"  # "memory" or "sqlite"
    transport: str = "stdio"       # "stdio" or "sse"

    log_level: str = "INFO"


settings = Settings()
