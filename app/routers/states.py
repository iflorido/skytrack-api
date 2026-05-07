import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from typing import Optional
from loguru import logger

from app.services.websocket_manager import ws_manager
from app.services.poller import poller
from app.services.opensky_client import opensky_client
from app.schemas.schemas import LiveStateResponse, StatsSchema
from app.core.config import settings

router = APIRouter(prefix="/states", tags=["states"])


@router.websocket("/live")
async def websocket_live(websocket: WebSocket):
    """
    WebSocket que hace push del estado de todas las aeronaves cada 10s.
    El cliente recibe datos sin necesidad de hacer polling REST.

    Mensaje recibido: LiveStateResponse JSON
    {
        "timestamp": 1234567890,
        "aircraft_count": 8432,
        "states": [...]
    }
    """
    await ws_manager.connect(websocket)
    try:
        while True:
            # Mantener la conexión viva esperando mensajes del cliente
            # (el cliente puede enviar "ping" o simplemente mantener abierto)
            try:
                data = await websocket.receive_text()
                if data == "ping":
                    await ws_manager.send_to(websocket, {"type": "pong", "timestamp": time.time()})
            except WebSocketDisconnect:
                break
            except Exception:
                break
    finally:
        await ws_manager.disconnect(websocket)


@router.get(
    "/current",
    response_model=LiveStateResponse,
    summary="Estado actual de todas las aeronaves",
    description="Devuelve el último snapshot obtenido del poller. "
                "Para datos en tiempo real usa el WebSocket /states/live.",
)
async def get_current_states(
    on_ground: Optional[bool] = Query(None, description="Filtrar por en tierra o en vuelo"),
    country: Optional[str] = Query(None, description="Filtrar por país de origen"),
    min_altitude: Optional[float] = Query(None, description="Altitud mínima en metros"),
    max_altitude: Optional[float] = Query(None, description="Altitud máxima en metros"),
    callsign: Optional[str] = Query(None, description="Filtrar por callsign (parcial)"),
):
    states = poller.last_states

    # Aplicar filtros
    if on_ground is not None:
        states = [s for s in states if s.on_ground == on_ground]
    if country:
        states = [s for s in states if s.origin_country and country.lower() in s.origin_country.lower()]
    if min_altitude is not None:
        states = [s for s in states if s.baro_altitude and s.baro_altitude >= min_altitude]
    if max_altitude is not None:
        states = [s for s in states if s.baro_altitude and s.baro_altitude <= max_altitude]
    if callsign:
        states = [s for s in states if s.callsign and callsign.upper() in s.callsign.upper()]

    return LiveStateResponse(
        timestamp=poller.last_timestamp or int(time.time()),
        aircraft_count=len(states),
        states=states,
    )


@router.get(
    "/aircraft/{icao24}",
    summary="Estado actual de una aeronave específica",
)
async def get_aircraft_state(icao24: str):
    """Devuelve el estado actual de una aeronave por su código ICAO24."""
    states = poller.last_states
    aircraft = next(
        (s for s in states if s.icao24.lower() == icao24.lower()),
        None
    )
    if not aircraft:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Aeronave {icao24} no encontrada en datos actuales")
    return aircraft


@router.get(
    "/stats",
    response_model=StatsSchema,
    summary="Estadísticas globales del tráfico aéreo actual",
)
async def get_stats():
    """Estadísticas agregadas del snapshot actual."""
    states = poller.last_states

    airborne = [s for s in states if not s.on_ground]
    on_ground = [s for s in states if s.on_ground]
    climbing = [s for s in states if s.is_climbing]
    descending = [s for s in states if s.is_descending]
    countries = set(s.origin_country for s in states if s.origin_country)

    return StatsSchema(
        total_aircraft_live=len(states),
        aircraft_airborne=len(airborne),
        aircraft_on_ground=len(on_ground),
        aircraft_climbing=len(climbing),
        aircraft_descending=len(descending),
        countries_represented=len(countries),
        last_update=poller.last_timestamp or int(time.time()),
        poll_interval_seconds=settings.POLL_INTERVAL_SECONDS,
        opensky_authenticated=settings.opensky_authenticated,
    )


@router.get(
    "/bbox",
    response_model=LiveStateResponse,
    summary="Aeronaves en un bounding box geográfico",
)
async def get_states_by_bbox(
    lamin: float = Query(..., description="Latitud mínima"),
    lomin: float = Query(..., description="Longitud mínima"),
    lamax: float = Query(..., description="Latitud máxima"),
    lomax: float = Query(..., description="Longitud máxima"),
):
    """
    Filtra aeronaves del snapshot actual dentro de un área geográfica.
    Para consultas en tiempo real con bbox propio, usa este endpoint.
    """
    states = poller.last_states
    filtered = [
        s for s in states
        if s.latitude is not None and s.longitude is not None
        and lamin <= s.latitude <= lamax
        and lomin <= s.longitude <= lomax
    ]
    return LiveStateResponse(
        timestamp=poller.last_timestamp or int(time.time()),
        aircraft_count=len(filtered),
        states=filtered,
    )