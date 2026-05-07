from sqlalchemy import (
    Column, String, Float, Boolean, Integer,
    BigInteger, Text, DateTime, Index, UniqueConstraint, PrimaryKeyConstraint
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.core.database import Base


class StateVector(Base):
    """
    Posición y estado de cada aeronave en tiempo real.
    Hypertable de TimescaleDB particionada por time_position.
    SQLAlchemy requiere PK — usamos clave compuesta icao24 + time_position.
    """
    __tablename__ = "state_vectors"

    icao24 = Column(String(6), nullable=False)
    time_position = Column(BigInteger, nullable=False)

    callsign = Column(String(8), nullable=True)
    origin_country = Column(String(100), nullable=True)

    longitude = Column(Float, nullable=True)
    latitude = Column(Float, nullable=True)
    baro_altitude = Column(Float, nullable=True)
    geo_altitude = Column(Float, nullable=True)
    on_ground = Column(Boolean, nullable=False, default=False)

    velocity = Column(Float, nullable=True)
    true_track = Column(Float, nullable=True)
    vertical_rate = Column(Float, nullable=True)

    squawk = Column(String(4), nullable=True)
    spi = Column(Boolean, nullable=True)
    position_source = Column(Integer, nullable=True)
    category = Column(Integer, nullable=True)

    last_contact = Column(BigInteger, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        PrimaryKeyConstraint("icao24", "time_position"),
        Index("ix_state_vectors_icao24", "icao24"),
        Index("ix_state_vectors_time", "time_position"),
    )


class Aircraft(Base):
    __tablename__ = "aircraft"

    icao24 = Column(String(6), primary_key=True)
    registration = Column(String(20), nullable=True)
    manufacturer = Column(String(100), nullable=True)
    model = Column(String(100), nullable=True)
    typecode = Column(String(10), nullable=True)
    serialnumber = Column(String(50), nullable=True)
    linenumber = Column(String(50), nullable=True)
    icaotypecode = Column(String(10), nullable=True)
    operator = Column(String(100), nullable=True)
    operatorcallsign = Column(String(20), nullable=True)
    operatoricao = Column(String(10), nullable=True)
    operatoriata = Column(String(10), nullable=True)
    owner = Column(String(100), nullable=True)
    categoryDescription = Column(String(100), nullable=True)
    built = Column(String(10), nullable=True)
    engines = Column(String(50), nullable=True)
    country = Column(String(100), nullable=True)

    last_seen = Column(BigInteger, nullable=True)
    last_callsign = Column(String(8), nullable=True)
    last_latitude = Column(Float, nullable=True)
    last_longitude = Column(Float, nullable=True)
    last_altitude = Column(Float, nullable=True)
    last_velocity = Column(Float, nullable=True)
    last_on_ground = Column(Boolean, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Flight(Base):
    __tablename__ = "flights"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    icao24 = Column(String(6), nullable=False, index=True)
    callsign = Column(String(8), nullable=True)

    first_seen = Column(BigInteger, nullable=False)
    est_departure_airport = Column(String(10), nullable=True)
    departure_airport_candidates = Column(JSONB, nullable=True)

    last_seen = Column(BigInteger, nullable=False)
    est_arrival_airport = Column(String(10), nullable=True)
    arrival_airport_candidates = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("icao24", "first_seen", name="uq_flight_icao24_time"),
        Index("ix_flights_departure_airport", "est_departure_airport"),
        Index("ix_flights_arrival_airport", "est_arrival_airport"),
        Index("ix_flights_first_seen", "first_seen"),
    )


class FlightTrack(Base):
    __tablename__ = "flight_tracks"

    icao24 = Column(String(6), nullable=False)
    timestamp = Column(BigInteger, nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    baro_altitude = Column(Float, nullable=True)
    true_track = Column(Float, nullable=True)
    on_ground = Column(Boolean, nullable=True)

    __table_args__ = (
        PrimaryKeyConstraint("icao24", "timestamp"),
        Index("ix_flight_tracks_icao24", "icao24"),
    )


class Airport(Base):
    __tablename__ = "airports"

    icao = Column(String(10), primary_key=True)
    iata = Column(String(5), nullable=True, index=True)
    name = Column(String(200), nullable=True)
    city = Column(String(100), nullable=True)
    country = Column(String(100), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    altitude = Column(Integer, nullable=True)
    timezone = Column(String(50), nullable=True)

    active_arrivals = Column(Integer, default=0)
    active_departures = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class PollerStats(Base):
    __tablename__ = "poller_stats"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    aircraft_count = Column(Integer, nullable=False, default=0)
    api_credits_remaining = Column(Integer, nullable=True)
    poll_duration_ms = Column(Integer, nullable=True)
    success = Column(Boolean, nullable=False, default=True)
    error_message = Column(Text, nullable=True)