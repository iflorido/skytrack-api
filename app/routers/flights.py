from fastapi import APIRouter, Query, HTTPException
from typing import Optional
import time

from app.services.opensky_client import opensky_client
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
    return {"icao24": icao24, "count": len(flights), "flights": flights}


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