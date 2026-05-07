from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger
from app.core.config import settings

PUBLIC_PATHS = {"/", "/health", "/metrics", "/docs", "/redoc", "/openapi.json"}
PUBLIC_PREFIXES = ("/docs/", "/redoc/")

# Rutas WebSocket — siempre permitidas (el navegador no envía Origin en WS igual que en HTTP)
WEBSOCKET_PREFIXES = ("/api/v1/states/live",)


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Rutas públicas
        if path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIXES):
            return await call_next(request)

        # WebSocket — permitir siempre (la seguridad la da CORS y el token de Cesium)
        if any(path.startswith(p) for p in WEBSOCKET_PREFIXES):
            return await call_next(request)

        # API Key si está configurada
        if settings.API_KEY:
            api_key = request.headers.get("X-API-Key")
            if api_key == settings.API_KEY:
                return await call_next(request)

        origin = request.headers.get("origin", "")
        referer = request.headers.get("referer", "")

        # Localhost en desarrollo
        local_origins = {"http://localhost", "http://127.0.0.1"}
        if any(origin.startswith(lo) or referer.startswith(lo) for lo in local_origins):
            return await call_next(request)

        # Orígenes permitidos
        allowed = settings.ALLOWED_ORIGINS
        origin_ok = any(origin.startswith(a) for a in allowed) if origin else False
        referer_ok = any(referer.startswith(a) for a in allowed) if referer else False

        if origin_ok or referer_ok:
            return await call_next(request)

        # Sin origen — bloquear
        if not origin and not referer:
            logger.warning(
                f"Petición bloqueada sin origen — "
                f"path: {path} — IP: {request.client.host if request.client else 'unknown'}"
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "Acceso denegado. Esta API es de uso exclusivo de flyskytrack.com"}
            )

        logger.warning(
            f"Origen no permitido — origin: '{origin}' referer: '{referer}' "
            f"path: {path} — IP: {request.client.host if request.client else 'unknown'}"
        )
        return JSONResponse(
            status_code=403,
            content={"detail": "Origen no autorizado"}
        )