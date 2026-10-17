import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "postgresql://postgres:postgres@localhost:5432/reserve_juggler"
    )
    BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8000"))
    BACKEND_HOST: str = os.getenv("BACKEND_HOST", "0.0.0.0")
    
    BASE_SAFETY_BUFFER: float = float(os.getenv("BASE_SAFETY_BUFFER", "50000.00"))
    UNCERTAINTY_MULTIPLIER: float = float(os.getenv("UNCERTAINTY_MULTIPLIER", "1.96"))
    MIN_SWEEP_THRESHOLD: float = float(os.getenv("MIN_SWEEP_THRESHOLD", "10000.00"))
    SWEEP_TARGET_EXCESS_RATIO: float = float(os.getenv("SWEEP_TARGET_EXCESS_RATIO", "1.05"))

    model_config = SettingsConfigDict(env_file=".env", extra="allow")

settings = Settings()
