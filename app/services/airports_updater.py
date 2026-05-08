import csv
import io
import math
import httpx
from loguru import logger
from sqlalchemy import text
from app.core.database import AsyncSessionLocal

AIRPORTS_CSV_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"

# Solo importar aeropuertos con estas categorías
VALID_TYPES = {"large_airport", "medium_airport", "small_airport"}


async def update_airports_from_csv() -> dict:
    """
    Descarga el CSV de OurAirports y actualiza la tabla airports.
    Se ejecuta automáticamente cada semana desde el scheduler.
    """
    logger.info("Iniciando actualización de aeropuertos desde OurAirports...")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(AIRPORTS_CSV_URL)
            response.raise_for_status()
            content = response.text
    except Exception as e:
        logger.error(f"Error descargando CSV de aeropuertos: {e}")
        return {"success": False, "error": str(e)}

    reader = csv.DictReader(io.StringIO(content))
    airports = []

    for row in reader:
        airport_type = row.get("type", "")
        if airport_type not in VALID_TYPES:
            continue

        try:
            lat = float(row["latitude_deg"]) if row.get("latitude_deg") else None
            lon = float(row["longitude_deg"]) if row.get("longitude_deg") else None
            alt = int(float(row["elevation_ft"])) if row.get("elevation_ft") else None
        except (ValueError, TypeError):
            continue

        icao = row.get("ident", "").strip()
        if not icao or len(icao) < 3:
            continue

        airports.append({
            "icao": icao,
            "iata": row.get("iata_code", "").strip() or None,
            "name": row.get("name", "").strip()[:200] or None,
            "city": row.get("municipality", "").strip()[:100] or None,
            "country": row.get("iso_country", "").strip()[:100] or None,
            "latitude": lat,
            "longitude": lon,
            "altitude": alt,
            "timezone": None,
        })

    if not airports:
        logger.warning("No se encontraron aeropuertos válidos en el CSV")
        return {"success": False, "error": "No valid airports found"}

    # Upsert en lotes de 500
    inserted = 0
    async with AsyncSessionLocal() as session:
        for i in range(0, len(airports), 500):
            batch = airports[i:i+500]
            await session.execute(
                text("""
                    INSERT INTO airports (icao, iata, name, city, country, latitude, longitude, altitude)
                    VALUES (:icao, :iata, :name, :city, :country, :latitude, :longitude, :altitude)
                    ON CONFLICT (icao) DO UPDATE SET
                        iata      = EXCLUDED.iata,
                        name      = EXCLUDED.name,
                        city      = EXCLUDED.city,
                        country   = EXCLUDED.country,
                        latitude  = EXCLUDED.latitude,
                        longitude = EXCLUDED.longitude,
                        altitude  = EXCLUDED.altitude,
                        updated_at = NOW()
                """),
                batch
            )
            inserted += len(batch)
        await session.commit()

    logger.info(f"Aeropuertos actualizados: {inserted} registros de {len(airports)} válidos")
    return {"success": True, "updated": inserted, "total_in_csv": len(airports)}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en km entre dos puntos geográficos."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


async def find_nearest_airport(lat: float, lon: float, max_km: float = 50.0) -> dict | None:
    """
    Busca el aeropuerto más cercano a una posición dada.
    Usa un bounding box SQL para eficiencia antes del cálculo Haversine exacto.
    """
    # Bounding box aproximado (1° lat ≈ 111km)
    delta = max_km / 111.0

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT icao, iata, name, city, country, latitude, longitude
                FROM airports
                WHERE latitude  BETWEEN :lat_min AND :lat_max
                  AND longitude BETWEEN :lon_min AND :lon_max
                  AND latitude IS NOT NULL
                  AND longitude IS NOT NULL
            """),
            {
                "lat_min": lat - delta,
                "lat_max": lat + delta,
                "lon_min": lon - delta,
                "lon_max": lon + delta,
            }
        )
        candidates = result.fetchall()

    if not candidates:
        return None

    nearest = None
    min_dist = float("inf")

    for airport in candidates:
        dist = haversine_km(lat, lon, airport.latitude, airport.longitude)
        if dist < min_dist:
            min_dist = dist
            nearest = airport

    if nearest and min_dist <= max_km:
        return {
            "icao": nearest.icao,
            "iata": nearest.iata,
            "name": nearest.name,
            "city": nearest.city,
            "country": nearest.country,
            "distance_km": round(min_dist, 1),
        }
    return None


async def get_flight_origin_destination(icao24: str, hours: int = 12) -> dict:
    """
    Calcula origen y destino de un vuelo desde nuestra BD de posiciones.
    - Origen: aeropuerto más cercano a la primera posición en tierra
    - Destino: aeropuerto más cercano a la posición actual (si en tierra)
              o None si aún está en vuelo
    """
    import time as time_module
    now = int(time_module.time())
    since = now - (hours * 3600)

    async with AsyncSessionLocal() as session:
        # Primera posición conocida (despegue)
        first_result = await session.execute(
            text("""
                SELECT latitude, longitude, on_ground, time_position
                FROM state_vectors
                WHERE icao24 = :icao24
                  AND time_position >= :since
                  AND latitude IS NOT NULL
                  AND longitude IS NOT NULL
                ORDER BY time_position ASC
                LIMIT 1
            """),
            {"icao24": icao24.lower(), "since": since}
        )
        first_pos = first_result.fetchone()

        # Última posición conocida
        last_result = await session.execute(
            text("""
                SELECT latitude, longitude, on_ground, time_position
                FROM state_vectors
                WHERE icao24 = :icao24
                  AND time_position >= :since
                  AND latitude IS NOT NULL
                  AND longitude IS NOT NULL
                ORDER BY time_position DESC
                LIMIT 1
            """),
            {"icao24": icao24.lower(), "since": since}
        )
        last_pos = last_result.fetchone()

    if not first_pos:
        return {"origin": None, "destination": None, "still_flying": None}

    origin = await find_nearest_airport(first_pos.latitude, first_pos.longitude, max_km=80)
    destination = None
    still_flying = True

    if last_pos and last_pos.on_ground:
        destination = await find_nearest_airport(last_pos.latitude, last_pos.longitude, max_km=50)
        still_flying = False
    elif last_pos:
        # En vuelo — aeropuerto más cercano a posición actual como estimación
        nearest = await find_nearest_airport(last_pos.latitude, last_pos.longitude, max_km=200)
        if nearest:
            nearest["estimated"] = True
        destination = nearest

    return {
        "origin": origin,
        "destination": destination,
        "still_flying": still_flying,
    }
