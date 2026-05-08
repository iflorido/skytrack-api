from fastapi import APIRouter, Query, HTTPException
from sqlalchemy import text
from app.services.opensky_client import opensky_client
from app.schemas.schemas import TrackSchema, TrackWaypointSchema
from app.core.database import AsyncSessionLocal
import time as time_module

router = APIRouter(prefix="/tracks", tags=["tracks"])


@router.get(
    "/history/{icao24}",
    response_model=TrackSchema,
    summary="Trayectoria histórica desde nuestra BD",
    description="Devuelve las posiciones guardadas en nuestra BD para una aeronave. "
                "Por defecto las últimas 6 horas.",
)
async def get_track_from_db(
    icao24: str,
    hours: int = Query(6, description="Horas hacia atrás (máx 24)", ge=1, le=24),
):
    now = int(time_module.time())
    since = now - (hours * 3600)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT
                    time_position,
                    latitude,
                    longitude,
                    baro_altitude,
                    true_track,
                    on_ground,
                    callsign
                FROM state_vectors
                WHERE icao24 = :icao24
                  AND time_position >= :since
                  AND latitude IS NOT NULL
                  AND longitude IS NOT NULL
                ORDER BY time_position ASC
            """),
            {"icao24": icao24.lower(), "since": since}
        )
        rows = result.fetchall()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No hay trayectoria histórica para {icao24} en las últimas {hours}h. "
                   "Es posible que el avión no haya sido detectado en ese período."
        )

    waypoints = [
        TrackWaypointSchema(
            timestamp=row.time_position,
            latitude=row.latitude,
            longitude=row.longitude,
            baro_altitude=row.baro_altitude,
            true_track=row.true_track,
            on_ground=row.on_ground,
        )
        for row in rows
    ]

    callsign = next((row.callsign for row in rows if row.callsign), None)

    return TrackSchema(
        icao24=icao24.lower(),
        callsign=callsign,
        start_time=rows[0].time_position,
        end_time=rows[-1].time_position,
        waypoints=waypoints,
    )


@router.get(
    "/{icao24}",
    response_model=TrackSchema,
    summary="Trayectoria desde OpenSky Network",
    description="time=0 para trayectoria en vivo desde OpenSky. "
                "Para trayectoria histórica desde nuestra BD usa /tracks/history/{icao24}",
)
async def get_track_from_opensky(
    icao24: str,
    time: int = Query(0, description="Unix timestamp (0 = live)"),
):
    data = await opensky_client.get_track_by_aircraft(icao24.lower(), time)
    if not data:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontró trayectoria para {icao24} en OpenSky. "
                   "Prueba el endpoint /tracks/history/{icao24} para datos de nuestra BD."
        )

    waypoints = [
        TrackWaypointSchema(
            timestamp=point[0],
            latitude=point[1],
            longitude=point[2],
            baro_altitude=point[3],
            true_track=point[4],
            on_ground=point[5],
        )
        for point in data.get("path", [])
    ]

    return TrackSchema(
        icao24=data.get("icao24", icao24),
        callsign=data.get("callsign"),
        start_time=data.get("startTime", 0),
        end_time=data.get("endTime", 0),
        waypoints=waypoints,
    )