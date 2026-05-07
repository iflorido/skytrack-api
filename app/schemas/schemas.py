from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ── Position source mapping ─────────────────────────────────────────
POSITION_SOURCE = {0: "ADS-B", 1: "ASTERIX", 2: "MLAT", 3: "FLARM"}

AIRCRAFT_CATEGORY = {
    0: "Unknown", 1: "No ADS-B info", 2: "Light (<15500 lbs)",
    3: "Small (15500-75000 lbs)", 4: "Large (75000-300000 lbs)",
    5: "High Vortex Large (B757)", 6: "Heavy (>300000 lbs)",
    7: "High Performance", 8: "Rotorcraft", 9: "Glider/Sailplane",
    10: "Lighter-than-air", 11: "Parachutist/Skydiver",
    12: "Ultralight/Hangglider", 13: "Reserved", 14: "UAV/Drone",
    15: "Space/Trans-atmospheric", 16: "Emergency Surface Vehicle",
    17: "Service Surface Vehicle", 18: "Point Obstacle",
    19: "Cluster Obstacle", 20: "Line Obstacle",
}


# ── State Vector ─────────────────────────────────────────────────────
class StateVectorSchema(BaseModel):
    icao24: str
    callsign: Optional[str] = None
    origin_country: Optional[str] = None
    time_position: Optional[int] = None
    last_contact: Optional[int] = None
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    baro_altitude: Optional[float] = None
    geo_altitude: Optional[float] = None
    on_ground: bool = False
    velocity: Optional[float] = None
    true_track: Optional[float] = None
    vertical_rate: Optional[float] = None
    squawk: Optional[str] = None
    spi: Optional[bool] = None
    position_source: Optional[int] = None
    position_source_name: Optional[str] = None
    category: Optional[int] = None
    category_name: Optional[str] = None

    # Campos calculados para el frontend
    altitude_ft: Optional[float] = None          # baro_altitude en pies
    velocity_kmh: Optional[float] = None         # velocidad en km/h
    vertical_rate_fpm: Optional[float] = None    # tasa vertical en ft/min
    is_climbing: Optional[bool] = None
    is_descending: Optional[bool] = None

    @classmethod
    def from_opensky_row(cls, row: list) -> "StateVectorSchema":
        """Convierte un array raw de OpenSky en el schema."""
        baro_alt = row[7]
        velocity = row[9]
        vertical_rate = row[11]
        pos_source = row[16]
        category = row[17] if len(row) > 17 else None

        return cls(
            icao24=row[0] or "",
            callsign=(row[1] or "").strip() or None,
            origin_country=row[2],
            time_position=row[3],
            last_contact=row[4],
            longitude=row[5],
            latitude=row[6],
            baro_altitude=baro_alt,
            geo_altitude=row[13],
            on_ground=row[8] or False,
            velocity=velocity,
            true_track=row[10],
            vertical_rate=vertical_rate,
            squawk=row[14],
            spi=row[15],
            position_source=pos_source,
            position_source_name=POSITION_SOURCE.get(pos_source) if pos_source is not None else None,
            category=category,
            category_name=AIRCRAFT_CATEGORY.get(category) if category is not None else None,
            # Conversiones de unidades
            altitude_ft=round(baro_alt * 3.28084, 0) if baro_alt else None,
            velocity_kmh=round(velocity * 3.6, 1) if velocity else None,
            vertical_rate_fpm=round(vertical_rate * 196.85, 0) if vertical_rate else None,
            is_climbing=vertical_rate > 0.5 if vertical_rate else None,
            is_descending=vertical_rate < -0.5 if vertical_rate else None,
        )

    model_config = {"from_attributes": True}


# ── Live response (WebSocket) ────────────────────────────────────────
class LiveStateResponse(BaseModel):
    timestamp: int
    aircraft_count: int
    states: list[StateVectorSchema]


# ── Flight ───────────────────────────────────────────────────────────
class FlightSchema(BaseModel):
    icao24: str
    callsign: Optional[str] = None
    first_seen: int
    last_seen: int
    est_departure_airport: Optional[str] = None
    est_arrival_airport: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Track waypoint ───────────────────────────────────────────────────
class TrackWaypointSchema(BaseModel):
    timestamp: int
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    baro_altitude: Optional[float] = None
    true_track: Optional[float] = None
    on_ground: Optional[bool] = None


class TrackSchema(BaseModel):
    icao24: str
    callsign: Optional[str] = None
    start_time: int
    end_time: int
    waypoints: list[TrackWaypointSchema]


# ── Airport ──────────────────────────────────────────────────────────
class AirportSchema(BaseModel):
    icao: str
    iata: Optional[str] = None
    name: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude: Optional[int] = None
    active_arrivals: int = 0
    active_departures: int = 0

    model_config = {"from_attributes": True}


# ── Stats ────────────────────────────────────────────────────────────
class StatsSchema(BaseModel):
    total_aircraft_live: int
    aircraft_airborne: int
    aircraft_on_ground: int
    aircraft_climbing: int
    aircraft_descending: int
    countries_represented: int
    last_update: int
    poll_interval_seconds: int
    opensky_authenticated: bool


# ── Health ───────────────────────────────────────────────────────────
class HealthSchema(BaseModel):
    status: str
    version: str
    database: bool
    opensky_authenticated: bool
    environment: str
    uptime_seconds: Optional[float] = None