from sqlalchemy import (
    Column, String, Float, Boolean, Integer,
    BigInteger, Text, DateTime, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.core.database import Base


class StateVector(Base):
    """
    Posición y estado de cada aeronave en tiempo real.
    Hypertable de TimescaleDB particionada por time_position.
    """
    __tablename__ = "state_vectors"

    # Clave compuesta: icao24 + timestamp (sin PK autoincremental en hypertables)
    icao24 = Column(String(6), nullable=False, index=True)
    time_position = Column(BigInteger, nullable=False)        # Unix timestamp (PK temporal)

    # Identificación
    callsign = Column(String(8), nullable=True)
    origin_country = Column(String(100), nullable=True)

    # Posición
    longitude = Column(Float, nullable=True)
    latitude = Column(Float, nullable=True)
    baro_altitude = Column(Float, nullable=True)              # metros
    geo_altitude = Column(Float, nullable=True)               # metros
    on_ground = Column(Boolean, nullable=False, default=False)

    # Movimiento
    velocity = Column(Float, nullable=True)                   # m/s
    true_track = Column(Float, nullable=True)                 # grados desde norte
    vertical_rate = Column(Float, nullable=True)              # m/s (+subiendo, -bajando)

    # Transponder
    squawk = Column(String(4), nullable=True)
    spi = Column(Boolean, nullable=True)                      # Special Purpose Indicator
    position_source = Column(Integer, nullable=True)          # 0=ADS-B,1=ASTERIX,2=MLAT,3=FLARM
    category = Column(Integer, nullable=True)                 # categoría aeronave (0-20)

    # Meta
    last_contact = Column(BigInteger, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_state_vectors_icao24_time", "icao24", "time_position"),
        Index("ix_state_vectors_time", "time_position"),
        # TimescaleDB requiere que time_position esté en la PK si se usa PK
        {"timescaledb_hypertable": False},                    # se gestiona en init_db()
    )


class Aircraft(Base):
    """
    Información estática de aeronaves conocidas.
    Se actualiza cuando se detecta nueva info.
    """
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

    # Último estado conocido (desnormalización para acceso rápido)
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
    """
    Vuelos completos con origen, destino y horarios.
    Datos del endpoint /flights de OpenSky.
    """
    __tablename__ = "flights"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    icao24 = Column(String(6), nullable=False, index=True)
    callsign = Column(String(8), nullable=True)

    # Origen
    first_seen = Column(BigInteger, nullable=False)
    est_departure_airport = Column(String(10), nullable=True)  # ICAO
    departure_airport_candidates = Column(JSONB, nullable=True)

    # Destino
    last_seen = Column(BigInteger, nullable=False)
    est_arrival_airport = Column(String(10), nullable=True)    # ICAO
    arrival_airport_candidates = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("icao24", "first_seen", name="uq_flight_icao24_time"),
        Index("ix_flights_departure_airport", "est_departure_airport"),
        Index("ix_flights_arrival_airport", "est_arrival_airport"),
        Index("ix_flights_first_seen", "first_seen"),
    )


class FlightTrack(Base):
    """
    Trayectorias (waypoints) de vuelos individuales.
    Hypertable de TimescaleDB particionada por timestamp.
    """
    __tablename__ = "flight_tracks"

    icao24 = Column(String(6), nullable=False, index=True)
    timestamp = Column(BigInteger, nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    baro_altitude = Column(Float, nullable=True)
    true_track = Column(Float, nullable=True)
    on_ground = Column(Boolean, nullable=True)

    __table_args__ = (
        Index("ix_flight_tracks_icao24_ts", "icao24", "timestamp"),
    )


class Airport(Base):
    """
    Información de aeropuertos para enrichment de datos.
    """
    __tablename__ = "airports"

    icao = Column(String(10), primary_key=True)
    iata = Column(String(5), nullable=True, index=True)
    name = Column(String(200), nullable=True)
    city = Column(String(100), nullable=True)
    country = Column(String(100), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    altitude = Column(Integer, nullable=True)                  # pies sobre nivel del mar
    timezone = Column(String(50), nullable=True)

    # Estadísticas actualizadas en tiempo real
    active_arrivals = Column(Integer, default=0)
    active_departures = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class PollerStats(Base):
    """
    Estadísticas del poller para monitorización interna.
    """
    __tablename__ = "poller_stats"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    aircraft_count = Column(Integer, nullable=False, default=0)
    api_credits_remaining = Column(Integer, nullable=True)
    poll_duration_ms = Column(Integer, nullable=True)
    success = Column(Boolean, nullable=False, default=True)
    error_message = Column(Text, nullable=True)