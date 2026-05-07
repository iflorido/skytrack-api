import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from loguru import logger

from app.core.config import settings
from app.core.logger import setup_logging
from app.core.database import init_db, check_db_connection
from app.services.opensky_client import opensky_client
from app.services.poller import poller
from app.services.websocket_manager import ws_manager
from app.routers import states, flights, tracks, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestiona el ciclo de vida de la aplicación."""
    setup_logging()
    logger.info(f"Arrancando {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Entorno: {settings.ENVIRONMENT}")

    # Verificar conexión a BD
    if not await check_db_connection():
        logger.error("No se puede conectar a la base de datos — abortando")
        raise RuntimeError("Database connection failed")

    # Inicializar tablas y TimescaleDB hypertables
    await init_db()

    # Iniciar cliente OpenSky
    await opensky_client.start()

    # Iniciar poller (comienza a obtener datos inmediatamente)
    await poller.start()

    # Tarea de heartbeat para WebSockets
    heartbeat_task = asyncio.create_task(_heartbeat_loop())

    logger.info("SkyTrack API lista para recibir conexiones ✓")
    logger.info(f"Docs disponibles en: /docs")

    yield  # ← aplicación corriendo

    # Shutdown
    logger.info("Apagando SkyTrack API...")
    heartbeat_task.cancel()
    await poller.stop()
    await opensky_client.stop()
    logger.info("Apagado completado")


async def _heartbeat_loop():
    """Envía ping a todos los WebSocket conectados cada 30s."""
    while True:
        await asyncio.sleep(settings.WS_HEARTBEAT_INTERVAL)
        if ws_manager.connection_count > 0:
            await ws_manager.broadcast_ping()


# ── Crear aplicación ─────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## SkyTrack API

API en tiempo real para rastreo de aeronaves usando datos de **OpenSky Network**.

### Características
- **WebSocket live** — recibe posiciones de ~10.000 aeronaves cada 10 segundos
- **REST endpoints** — consulta estados, vuelos, trayectorias y estadísticas
- **Histórico** — datos persistidos en PostgreSQL con TimescaleDB
- **Filtros geográficos** — bounding box para zonas específicas

### Endpoints principales
- `WS /states/live` — stream en tiempo real
- `GET /states/current` — snapshot actual con filtros
- `GET /flights/*` — vuelos históricos
- `GET /tracks/{icao24}` — trayectoria de una aeronave
    """,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["api.flyskytrack.com", "localhost", "127.0.0.1", "*"],
)

# ── Routers ───────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(states.router, prefix="/api/v1")
app.include_router(flights.router, prefix="/api/v1")
app.include_router(tracks.router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
async def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "websocket": "/api/v1/states/live",
        "status": "/health",
    }