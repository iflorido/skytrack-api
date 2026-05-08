from fastapi import APIRouter, Query, HTTPException
from typing import Optional
import time

from app.services.opensky_client import opensky_client
from app.services.aviationstack import aviationstack_service
from app.schemas.schemas import FlightSchema, TrackSchema, TrackWaypointSchema

router = APIRouter(prefix="/flights", tags=["flights"])


@router.get(
    "/interval",
    summary="Vuelos en un intervalo de tiempo",
    description="Máximo 2 horas de rango. Requiere autenticación OpenSky para datos recientes.",
)
async def get_flights_by_interval(
    begin: int = Query(..., description="Unix timestamp inicio"),
    end: int = Query(..., description="Unix timestamp fin (máx begin + 7200)"),
):
    if end - begin > 7200:
        raise HTTPException(status_code=400, detail="El intervalo no puede superar 2 horas (7200 segundos)")
    if end <= begin:
        raise HTTPException(status_code=400, detail="end debe ser mayor que begin")

    flights = await opensky_client.get_flights_by_interval(begin, end)
    return {"count": len(flights), "flights": flights}


@router.get(
    "/aircraft/{icao24}",
    summary="Vuelos históricos de una aeronave",
    description="Máximo 2 días de rango. Solo vuelos del día anterior o anterior.",
)
async def get_flights_by_aircraft(
    icao24: str,
    begin: int = Query(..., description="Unix timestamp inicio"),
    end: int = Query(..., description="Unix timestamp fin"),
):
    if end - begin > 172800:
        raise HTTPException(status_code=400, detail="El intervalo no puede superar 2 días")

    flights = await opensky_client.get_flights_by_aircraft(icao24.lower(), begin, end)
    if not flights:
        raise HTTPException(status_code=404, detail=f"No se encontraron vuelos para {icao24}")
    # Ordenar por firstSeen descendente (más reciente primero)
    flights_sorted = sorted(flights, key=lambda f: f.get("firstSeen", 0), reverse=True)
    return {"icao24": icao24, "count": len(flights_sorted), "flights": flights_sorted}


@router.get(
    "/arrivals/{airport}",
    summary="Llegadas a un aeropuerto",
)
async def get_arrivals(
    airport: str,
    begin: int = Query(..., description="Unix timestamp inicio"),
    end: int = Query(..., description="Unix timestamp fin"),
):
    if end - begin > 172800:
        raise HTTPException(status_code=400, detail="El intervalo no puede superar 2 días")

    flights = await opensky_client.get_arrivals_by_airport(airport.upper(), begin, end)
    return {"airport": airport.upper(), "count": len(flights), "arrivals": flights}


@router.get(
    "/departures/{airport}",
    summary="Salidas de un aeropuerto",
)
async def get_departures(
    airport: str,
    begin: int = Query(..., description="Unix timestamp inicio"),
    end: int = Query(..., description="Unix timestamp fin"),
):
    if end - begin > 172800:
        raise HTTPException(status_code=400, detail="El intervalo no puede superar 2 días")

    flights = await opensky_client.get_departures_by_airport(airport.upper(), begin, end)
    return {"airport": airport.upper(), "count": len(flights), "departures": flights}


@router.get(
    "/info/{callsign}",
    summary="Información enriquecida de un vuelo via AviationStack",
    description="Devuelve origen, destino, horarios y aerolínea. Usa caché de 1h para conservar el límite de peticiones.",
)
async def get_flight_info(callsign: str):
    """Busca información de vuelo por callsign ICAO o IATA."""
    result = await aviationstack_service.get_flight_info(callsign.strip())
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontró información para el vuelo {callsign}. "
                   "Puede que el callsign no sea reconocido por AviationStack o se haya agotado el límite mensual."
        )
    return result


@router.get(
    "/origin-destination/{icao24}",
    summary="Origen y destino calculados desde nuestra BD",
    description="Calcula el aeropuerto de origen y destino buscando "
                "las primeras/últimas posiciones del avión en nuestra BD "
                "y comparándolas con nuestra base de aeropuertos (OurAirports).",
)
async def get_origin_destination(
    icao24: str,
    hours: int = Query(12, description="Horas de histórico a analizar", ge=1, le=24),
):
    from app.services.airports_updater import get_flight_origin_destination
    result = await get_flight_origin_destination(icao24.lower(), hours)
    if not result["origin"] and not result["destination"]:
        raise HTTPException(
            status_code=404,
            detail=f"No hay suficientes datos para calcular origen/destino de {icao24}"
        )
    return result


@router.post(
    "/airports/update",
    summary="Forzar actualización manual de aeropuertos",
    description="Descarga el CSV de OurAirports y actualiza la BD. "
                "Se ejecuta automáticamente cada semana.",
)
async def force_airports_update():
    from app.services.airports_updater import update_airports_from_csv
    result = await update_airports_from_csv()
    return result