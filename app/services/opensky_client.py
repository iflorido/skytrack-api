import httpx
from datetime import datetime, timedelta
from typing import Optional
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
from app.core.config import settings
from app.schemas.schemas import StateVectorSchema


class TokenManager:
    """Gestiona el token OAuth2 de OpenSky con refresh automático."""

    TOKEN_REFRESH_MARGIN = 60  # segundos antes de expirar para refrescar

    def __init__(self):
        self.token: Optional[str] = None
        self.expires_at: Optional[datetime] = None

    async def get_token(self, client: httpx.AsyncClient) -> Optional[str]:
        if not settings.opensky_authenticated:
            return None
        if self.token and self.expires_at and datetime.now() < self.expires_at:
            return self.token
        return await self._refresh(client)

    async def _refresh(self, client: httpx.AsyncClient) -> Optional[str]:
        try:
            response = await client.post(
                settings.OPENSKY_AUTH_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.OPENSKY_CLIENT_ID,
                    "client_secret": settings.OPENSKY_CLIENT_SECRET,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15.0,
            )
            response.raise_for_status()
            data = response.json()
            self.token = data["access_token"]
            expires_in = data.get("expires_in", 1800)
            self.expires_at = datetime.now() + timedelta(
                seconds=expires_in - self.TOKEN_REFRESH_MARGIN
            )
            logger.info(f"Token OpenSky renovado — expira en {expires_in}s")
            return self.token
        except Exception as e:
            logger.error(f"Error renovando token OpenSky: {e}")
            self.token = None
            self.expires_at = None
            return None

    def get_headers(self, token: Optional[str]) -> dict:
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}


class OpenSkyClient:
    """
    Cliente async para la API REST de OpenSky Network.
    Soporta modo autenticado (OAuth2) y anónimo.
    """

    def __init__(self):
        self.token_manager = TokenManager()
        self._client: Optional[httpx.AsyncClient] = None

    async def start(self):
        self._client = httpx.AsyncClient(
            base_url=settings.OPENSKY_BASE_URL,
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
        mode = "autenticado (OAuth2)" if settings.opensky_authenticated else "anónimo"
        logger.info(f"OpenSkyClient iniciado — modo: {mode}")

    async def stop(self):
        if self._client:
            await self._client.aclose()
            logger.info("OpenSkyClient cerrado")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def get_all_states(
        self,
        bbox: Optional[dict] = None,
        extended: bool = True,
    ) -> tuple[int, list[StateVectorSchema]]:
        """
        Obtiene todos los state vectors del network.

        Args:
            bbox: dict con lamin, lomin, lamax, lomax (opcional)
            extended: True para incluir categoría de aeronave (campo 17)

        Returns:
            (timestamp, lista de StateVectorSchema)
        """
        token = await self.token_manager.get_token(self._client)
        headers = self.token_manager.get_headers(token)

        params = {"extended": 1} if extended else {}

        if bbox:
            params.update({
                "lamin": bbox["lamin"],
                "lomin": bbox["lomin"],
                "lamax": bbox["lamax"],
                "lomax": bbox["lomax"],
            })
        elif settings.POLL_BBOX_ENABLED:
            params.update({
                "lamin": settings.POLL_BBOX_LAMIN,
                "lomin": settings.POLL_BBOX_LOMIN,
                "lamax": settings.POLL_BBOX_LAMAX,
                "lomax": settings.POLL_BBOX_LOMAX,
            })

        response = await self._client.get(
            "/states/all",
            params=params,
            headers=headers,
        )

        # Gestión de rate limit
        remaining = response.headers.get("X-Rate-Limit-Remaining")
        if remaining:
            logger.debug(f"OpenSky créditos restantes: {remaining}")

        if response.status_code == 429:
            retry_after = response.headers.get("X-Rate-Limit-Retry-After-Seconds", 60)
            logger.warning(f"Rate limit OpenSky — esperar {retry_after}s")
            raise httpx.HTTPStatusError(
                "Rate limit", request=response.request, response=response
            )

        if response.status_code == 401:
            logger.warning("Token expirado — forzando refresh")
            self.token_manager.token = None
            raise httpx.HTTPStatusError(
                "Unauthorized", request=response.request, response=response
            )

        response.raise_for_status()
        data = response.json()

        timestamp = data.get("time", 0)
        raw_states = data.get("states") or []

        states = []
        for row in raw_states:
            try:
                # Filtrar aeronaves sin posición válida
                if row[5] is None or row[6] is None:
                    continue
                states.append(StateVectorSchema.from_opensky_row(row))
            except Exception as e:
                logger.debug(f"Error parseando state vector {row[0]}: {e}")
                continue

        logger.info(f"OpenSky: {len(states)} aeronaves con posición válida (ts={timestamp})")
        return timestamp, states

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=2, max=8))
    async def get_flights_by_interval(
        self, begin: int, end: int
    ) -> list[dict]:
        """Vuelos en un intervalo de tiempo (máx 2 horas)."""
        token = await self.token_manager.get_token(self._client)
        headers = self.token_manager.get_headers(token)

        response = await self._client.get(
            "/flights/all",
            params={"begin": begin, "end": end},
            headers=headers,
        )
        if response.status_code == 404:
            return []
        response.raise_for_status()
        return response.json() or []

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=2, max=8))
    async def get_flights_by_aircraft(
        self, icao24: str, begin: int, end: int
    ) -> list[dict]:
        """Vuelos de una aeronave específica."""
        token = await self.token_manager.get_token(self._client)
        headers = self.token_manager.get_headers(token)

        response = await self._client.get(
            "/flights/aircraft",
            params={"icao24": icao24.lower(), "begin": begin, "end": end},
            headers=headers,
        )
        if response.status_code == 404:
            return []
        response.raise_for_status()
        return response.json() or []

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=2, max=8))
    async def get_arrivals_by_airport(
        self, airport: str, begin: int, end: int
    ) -> list[dict]:
        """Llegadas a un aeropuerto en un intervalo."""
        token = await self.token_manager.get_token(self._client)
        headers = self.token_manager.get_headers(token)

        response = await self._client.get(
            "/flights/arrival",
            params={"airport": airport.upper(), "begin": begin, "end": end},
            headers=headers,
        )
        if response.status_code == 404:
            return []
        response.raise_for_status()
        return response.json() or []

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=2, max=8))
    async def get_departures_by_airport(
        self, airport: str, begin: int, end: int
    ) -> list[dict]:
        """Salidas de un aeropuerto en un intervalo."""
        token = await self.token_manager.get_token(self._client)
        headers = self.token_manager.get_headers(token)

        response = await self._client.get(
            "/flights/departure",
            params={"airport": airport.upper(), "begin": begin, "end": end},
            headers=headers,
        )
        if response.status_code == 404:
            return []
        response.raise_for_status()
        return response.json() or []

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=2, max=8))
    async def get_track_by_aircraft(
        self, icao24: str, time: int = 0
    ) -> Optional[dict]:
        """Trayectoria de una aeronave (time=0 para live)."""
        token = await self.token_manager.get_token(self._client)
        headers = self.token_manager.get_headers(token)

        response = await self._client.get(
            "/tracks/all",
            params={"icao24": icao24.lower(), "time": time},
            headers=headers,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()


# Instancia global compartida
opensky_client = OpenSkyClient()