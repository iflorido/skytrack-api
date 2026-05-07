from fastapi import APIRouter
from app.core.database import check_db_connection
from app.core.config import settings
from app.services.poller import poller
from app.services.websocket_manager import ws_manager
from app.schemas.schemas import HealthSchema

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthSchema, summary="Estado del sistema")
async def health_check():
    db_ok = await check_db_connection()
    return HealthSchema(
        status="ok" if db_ok else "degraded",
        version=settings.APP_VERSION,
        database=db_ok,
        opensky_authenticated=settings.opensky_authenticated,
        environment=settings.ENVIRONMENT,
        uptime_seconds=round(poller.uptime_seconds, 1),
    )


@router.get("/metrics", summary="Métricas internas del sistema")
async def get_metrics():
    return {
        "poller": {
            "running": poller.is_running,
            "last_timestamp": poller.last_timestamp,
            "aircraft_count": len(poller.last_states),
            "uptime_seconds": round(poller.uptime_seconds, 1),
        },
        "websocket": {
            "active_connections": ws_manager.connection_count,
        },
        "config": {
            "poll_interval_seconds": settings.POLL_INTERVAL_SECONDS,
            "opensky_authenticated": settings.opensky_authenticated,
            "bbox_enabled": settings.POLL_BBOX_ENABLED,
            "environment": settings.ENVIRONMENT,
        },
    }