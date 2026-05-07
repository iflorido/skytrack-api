import asyncio
import time
from typing import Optional
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.services.opensky_client import opensky_client
from app.services.websocket_manager import ws_manager
from app.schemas.schemas import StateVectorSchema, LiveStateResponse
from app.models.models import StateVector, Aircraft, PollerStats


class PollerService:
    """
    Servicio central de polling a OpenSky Network.

    - Se ejecuta cada POLL_INTERVAL_SECONDS segundos
    - Obtiene todos los state vectors
    - Persiste en BD (state_vectors + aircraft)
    - Hace broadcast a todos los WebSocket conectados
    - Registra estadísticas de cada poll
    """

    def __init__(self):
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._last_states: list[StateVectorSchema] = []
        self._last_timestamp: int = 0
        self._poll_count: int = 0
        self._start_time: float = 0.0

    async def start(self):
        if self._running:
            logger.warning("Poller ya está en ejecución")
            return
        self._running = True
        self._start_time = time.time()
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(
            f"Poller iniciado — intervalo: {settings.POLL_INTERVAL_SECONDS}s "
            f"— modo: {'autenticado' if settings.opensky_authenticated else 'anónimo'}"
        )

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"Poller detenido — total polls: {self._poll_count}")

    async def _poll_loop(self):
        """Bucle principal de polling."""
        while self._running:
            poll_start = time.time()
            success = False
            error_msg = None
            aircraft_count = 0

            try:
                timestamp, states = await opensky_client.get_all_states(extended=True)

                if states:
                    self._last_states = states
                    self._last_timestamp = timestamp
                    aircraft_count = len(states)
                    self._poll_count += 1

                    # Broadcast a WebSocket
                    response = LiveStateResponse(
                        timestamp=timestamp,
                        aircraft_count=aircraft_count,
                        states=states,
                    )
                    await ws_manager.broadcast(response)

                    # Persistir en BD (en background para no bloquear)
                    asyncio.create_task(
                        self._persist_states(timestamp, states)
                    )

                    success = True
                    logger.debug(
                        f"Poll #{self._poll_count} — "
                        f"{aircraft_count} aeronaves — "
                        f"{len(ws_manager.active_connections)} clientes WS"
                    )

            except Exception as e:
                error_msg = str(e)
                logger.error(f"Error en poll: {e}")

            # Registrar estadísticas
            poll_duration_ms = int((time.time() - poll_start) * 1000)
            asyncio.create_task(
                self._save_poll_stats(aircraft_count, poll_duration_ms, success, error_msg)
            )

            # Esperar hasta el próximo intervalo
            elapsed = time.time() - poll_start
            sleep_time = max(0, settings.POLL_INTERVAL_SECONDS - elapsed)
            await asyncio.sleep(sleep_time)

    async def _persist_states(self, timestamp: int, states: list[StateVectorSchema]):
        """Persiste los state vectors en BD de forma eficiente con bulk insert."""
        try:
            async with AsyncSessionLocal() as session:
                # Bulk insert de state_vectors usando INSERT ... ON CONFLICT DO NOTHING
                # para evitar duplicados si el poller se solapa
                values = []
                for s in states:
                    if s.latitude is None or s.longitude is None:
                        continue
                    values.append({
                        "icao24": s.icao24,
                        "time_position": s.time_position or timestamp,
                        "callsign": s.callsign,
                        "origin_country": s.origin_country,
                        "longitude": s.longitude,
                        "latitude": s.latitude,
                        "baro_altitude": s.baro_altitude,
                        "geo_altitude": s.geo_altitude,
                        "on_ground": s.on_ground,
                        "velocity": s.velocity,
                        "true_track": s.true_track,
                        "vertical_rate": s.vertical_rate,
                        "squawk": s.squawk,
                        "spi": s.spi,
                        "position_source": s.position_source,
                        "category": s.category,
                        "last_contact": s.last_contact,
                    })

                if values:
                    await session.execute(
                        text("""
                            INSERT INTO state_vectors (
                                icao24, time_position, callsign, origin_country,
                                longitude, latitude, baro_altitude, geo_altitude,
                                on_ground, velocity, true_track, vertical_rate,
                                squawk, spi, position_source, category, last_contact
                            ) VALUES (
                                :icao24, :time_position, :callsign, :origin_country,
                                :longitude, :latitude, :baro_altitude, :geo_altitude,
                                :on_ground, :velocity, :true_track, :vertical_rate,
                                :squawk, :spi, :position_source, :category, :last_contact
                            )
                            ON CONFLICT DO NOTHING
                        """),
                        values,
                    )

                # Upsert de tabla aircraft (último estado conocido)
                aircraft_values = []
                for s in states:
                    if s.latitude is None or s.longitude is None:
                        continue
                    aircraft_values.append({
                        "icao24": s.icao24,
                        "last_seen": s.time_position or timestamp,
                        "last_callsign": s.callsign,
                        "last_latitude": s.latitude,
                        "last_longitude": s.longitude,
                        "last_altitude": s.baro_altitude,
                        "last_velocity": s.velocity,
                        "last_on_ground": s.on_ground,
                    })

                if aircraft_values:
                    await session.execute(
                        text("""
                            INSERT INTO aircraft (
                                icao24, last_seen, last_callsign,
                                last_latitude, last_longitude,
                                last_altitude, last_velocity, last_on_ground
                            ) VALUES (
                                :icao24, :last_seen, :last_callsign,
                                :last_latitude, :last_longitude,
                                :last_altitude, :last_velocity, :last_on_ground
                            )
                            ON CONFLICT (icao24) DO UPDATE SET
                                last_seen = EXCLUDED.last_seen,
                                last_callsign = EXCLUDED.last_callsign,
                                last_latitude = EXCLUDED.last_latitude,
                                last_longitude = EXCLUDED.last_longitude,
                                last_altitude = EXCLUDED.last_altitude,
                                last_velocity = EXCLUDED.last_velocity,
                                last_on_ground = EXCLUDED.last_on_ground,
                                updated_at = NOW()
                        """),
                        aircraft_values,
                    )

                await session.commit()

        except Exception as e:
            logger.error(f"Error persistiendo estados en BD: {e}")

    async def _save_poll_stats(
        self,
        aircraft_count: int,
        duration_ms: int,
        success: bool,
        error_msg: Optional[str],
    ):
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(
                    text("""
                        INSERT INTO poller_stats
                            (aircraft_count, poll_duration_ms, success, error_message)
                        VALUES
                            (:aircraft_count, :poll_duration_ms, :success, :error_message)
                    """),
                    {
                        "aircraft_count": aircraft_count,
                        "poll_duration_ms": duration_ms,
                        "success": success,
                        "error_message": error_msg,
                    },
                )
                await session.commit()
        except Exception as e:
            logger.debug(f"Error guardando stats de poll: {e}")

    @property
    def last_states(self) -> list[StateVectorSchema]:
        return self._last_states

    @property
    def last_timestamp(self) -> int:
        return self._last_timestamp

    @property
    def uptime_seconds(self) -> float:
        if self._start_time:
            return time.time() - self._start_time
        return 0.0

    @property
    def is_running(self) -> bool:
        return self._running


# Instancia global compartida
poller = PollerService()