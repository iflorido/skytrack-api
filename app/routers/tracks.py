from fastapi import APIRouter, Query, HTTPException
from app.services.opensky_client import opensky_client
from app.schemas.schemas import TrackSchema, TrackWaypointSchema

router = APIRouter(prefix="/tracks", tags=["tracks"])


@router.get(
    "/{icao24}",
    summary="Trayectoria de una aeronave",
    description="time=0 para trayectoria en vivo. "
                "Cualquier Unix timestamp entre inicio y fin de un vuelo conocido para histórico.",
)
async def get_track(
    icao24: str,
    time: int = Query(0, description="Unix timestamp (0 = live)"),
):
    data = await opensky_client.get_track_by_aircraft(icao24.lower(), time)
    if not data:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontró trayectoria para {icao24}. "
                   "El vuelo puede no estar activo o los datos no estar disponibles."
        )

    waypoints = []
    for point in data.get("path", []):
        waypoints.append(TrackWaypointSchema(
            timestamp=point[0],
            latitude=point[1],
            longitude=point[2],
            baro_altitude=point[3],
            true_track=point[4],
            on_ground=point[5],
        ))

    return TrackSchema(
        icao24=data.get("icao24", icao24),
        callsign=data.get("callsign"),
        start_time=data.get("startTime", 0),
        end_time=data.get("endTime", 0),
        waypoints=waypoints,
    )