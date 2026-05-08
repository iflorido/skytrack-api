import httpx
import time
from typing import Optional
from loguru import logger
from app.core.config import settings

# Caché en memoria — evita gastar peticiones en el mismo vuelo
# { callsign: (timestamp, data) }
_cache: dict[str, tuple[float, dict]] = {}
CACHE_TTL = 3600  # 1 hora — los planes de vuelo no cambian frecuentemente


class AviationStackService:
    BASE_URL = "https://api.aviationstack.com/v1"

    async def get_flight_info(self, callsign: str) -> Optional[dict]:
        """
        Obtiene información de un vuelo por callsign (ICAO flight number).
        Usa caché de 1 hora para conservar las 100 peticiones mensuales.
        """
        if not settings.AVIATIONSTACK_KEY:
            return None

        callsign = callsign.strip().upper()

        # Comprobar caché
        if callsign in _cache:
            ts, data = _cache[callsign]
            if time.time() - ts < CACHE_TTL:
                logger.debug(f"AviationStack cache hit: {callsign}")
                return data

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}/flights",
                    params={
                        "access_key": settings.AVIATIONSTACK_KEY,
                        "flight_icao": callsign,
                        "limit": 1,
                    }
                )
                response.raise_for_status()
                data = response.json()

            flights = data.get("data", [])
            if not flights:
                # Intentar con flight_iata si no hay resultado con ICAO
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(
                        f"{self.BASE_URL}/flights",
                        params={
                            "access_key": settings.AVIATIONSTACK_KEY,
                            "flight_iata": callsign,
                            "limit": 1,
                        }
                    )
                    response.raise_for_status()
                    data = response.json()
                flights = data.get("data", [])

            if not flights:
                logger.info(f"AviationStack: sin datos para {callsign}")
                return None

            flight = flights[0]
            result = self._parse_flight(flight)

            # Guardar en caché
            _cache[callsign] = (time.time(), result)
            logger.info(f"AviationStack: {callsign} → {result.get('departure_icao')} → {result.get('arrival_icao')}")
            return result

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("AviationStack: límite de peticiones alcanzado")
            else:
                logger.error(f"AviationStack HTTP error: {e}")
            return None
        except Exception as e:
            logger.error(f"AviationStack error: {e}")
            return None

    def _parse_flight(self, flight: dict) -> dict:
        dep = flight.get("departure", {}) or {}
        arr = flight.get("arrival", {}) or {}
        fl  = flight.get("flight", {}) or {}
        al  = flight.get("airline", {}) or {}

        return {
            # Aeropuertos
            "departure_iata":      dep.get("iata"),
            "departure_icao":      dep.get("icao"),
            "departure_airport":   dep.get("airport"),
            "departure_scheduled": dep.get("scheduled"),
            "departure_actual":    dep.get("actual"),
            "departure_delay":     dep.get("delay"),

            "arrival_iata":        arr.get("iata"),
            "arrival_icao":        arr.get("icao"),
            "arrival_airport":     arr.get("airport"),
            "arrival_scheduled":   arr.get("scheduled"),
            "arrival_estimated":   arr.get("estimated"),
            "arrival_delay":       arr.get("delay"),

            # Vuelo
            "flight_iata":         fl.get("iata"),
            "flight_icao":         fl.get("icao"),
            "flight_number":       fl.get("number"),

            # Aerolínea
            "airline_name":        al.get("name"),
            "airline_iata":        al.get("iata"),

            # Estado
            "flight_status":       flight.get("flight_status"),
        }

    def cache_stats(self) -> dict:
        return {
            "cached_flights": len(_cache),
            "entries": list(_cache.keys()),
        }


aviationstack_service = AviationStackService()