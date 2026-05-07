from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # App
    APP_NAME: str = "SkyTrack API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"

    # Database
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 5432
    DB_NAME: str = "admin_skytrack_db"
    DB_USER: str = "admin_userflyskytrack"
    DB_PASSWORD: str

    # OpenSky Network
    OPENSKY_CLIENT_ID: Optional[str] = None
    OPENSKY_CLIENT_SECRET: Optional[str] = None
    OPENSKY_BASE_URL: str = "https://opensky-network.org/api"
    OPENSKY_AUTH_URL: str = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"

    # Polling
    POLL_INTERVAL_SECONDS: int = 10        # cada 10s con auth, 15s sin auth
    POLL_BBOX_ENABLED: bool = False        # True = zona, False = global
    POLL_BBOX_LAMIN: float = 25.0          # bounding box global por defecto
    POLL_BBOX_LOMIN: float = -25.0
    POLL_BBOX_LAMAX: float = 72.0
    POLL_BBOX_LOMAX: float = 45.0

    # CORS
    CORS_ORIGINS: list[str] = [
        "https://flyskytrack.com",
        "https://www.flyskytrack.com",
        "http://localhost:5173",           # Vite dev server
        "http://localhost:3000",
    ]

    # WebSocket
    WS_HEARTBEAT_INTERVAL: int = 30       # segundos entre pings

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def DATABASE_URL_SYNC(self) -> str:
        """Para Alembic (síncrono)"""
        return (
            f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def opensky_authenticated(self) -> bool:
        return bool(self.OPENSKY_CLIENT_ID and self.OPENSKY_CLIENT_SECRET)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()