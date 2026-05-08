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
    POLL_INTERVAL_SECONDS: int = 10
    POLL_BBOX_ENABLED: bool = False
    POLL_BBOX_LAMIN: float = 25.0
    POLL_BBOX_LOMIN: float = -25.0
    POLL_BBOX_LAMAX: float = 72.0
    POLL_BBOX_LOMAX: float = 45.0

    # CORS — orígenes permitidos para peticiones desde navegador
    CORS_ORIGINS: list[str] = [
        "https://flyskytrack.com",
        "https://www.flyskytrack.com",
        "http://localhost:5173",
        "http://localhost:3000",
    ]

    # Seguridad — orígenes permitidos (referer/origin header validation)
    ALLOWED_ORIGINS: list[str] = [
        "https://flyskytrack.com",
        "https://www.flyskytrack.com",
        "https://api.flyskytrack.com",
    ]

    # AviationStack
    AVIATIONSTACK_KEY: Optional[str] = None

    # API Key interna para el frontend
    # Configúrala como variable de entorno en Docker: API_KEY=tu_clave_secreta
    API_KEY: Optional[str] = None

    # WebSocket
    WS_HEARTBEAT_INTERVAL: int = 30

    @property
    def DATABASE_URL(self) -> str:
        from urllib.parse import quote_plus
        password = quote_plus(self.DB_PASSWORD)
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{password}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def DATABASE_URL_SYNC(self) -> str:
        from urllib.parse import quote_plus
        password = quote_plus(self.DB_PASSWORD)
        return (
            f"postgresql+psycopg2://{self.DB_USER}:{password}"
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