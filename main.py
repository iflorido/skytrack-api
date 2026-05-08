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
    setup_logging()
    logger.info(f"Arrancando {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Entorno: {settings.ENVIRONMENT}")

    if not await check_db_connection():
        logger.error("No se puede conectar a la base de datos — abortando")
        raise RuntimeError("Database connection failed")

    await init_db()
    await opensky_client.start()
    await poller.start()

    # Actualizar aeropuertos al arrancar si la tabla está vacía
    asyncio.create_task(_init_airports())

    heartbeat_task = asyncio.create_task(_heartbeat_loop())

    logger.info("SkyTrack API lista para recibir conexiones ✓")
    logger.info("Docs disponibles en: /docs")

    yield

    logger.info("Apagando SkyTrack API...")
    heartbeat_task.cancel()
    await poller.stop()
    await opensky_client.stop()
    logger.info("Apagado completado")


async def _init_airports():
    """Actualiza aeropuertos al arrancar si la tabla está vacía."""
    from app.services.airports_updater import update_airports_from_csv
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT COUNT(*) FROM airports"))
        count = result.scalar()
    if count == 0:
        logger.info("Tabla airports vacía — descargando desde OurAirports...")
        await update_airports_from_csv()
    else:
        logger.info(f"Tabla airports ya tiene {count} registros")

    # Programar actualización semanal
    asyncio.create_task(_weekly_airports_update())


async def _weekly_airports_update():
    """Actualiza aeropuertos cada 7 días."""
    from app.services.airports_updater import update_airports_from_csv
    while True:
        await asyncio.sleep(7 * 24 * 3600)  # 7 días
        logger.info("Actualización semanal de aeropuertos...")
        await update_airports_from_csv()


async def _heartbeat_loop():
    while True:
        await asyncio.sleep(settings.WS_HEARTBEAT_INTERVAL)
        if ws_manager.connection_count > 0:
            await ws_manager.broadcast_ping()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## SkyTrack API

API en tiempo real para rastreo de aeronaves usando datos de **OpenSky Network**.

### Endpoints principales
- `WS /api/v1/states/live` — stream en tiempo real
- `GET /api/v1/states/current` — snapshot actual con filtros
- `GET /api/v1/flights/*` — vuelos históricos
- `GET /api/v1/tracks/{icao24}` — trayectoria de una aeronave
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