from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger
from app.core.config import settings


# Rutas que nunca se bloquean independientemente del origen
PUBLIC_PATHS = {"/", "/health", "/metrics", "/docs", "/redoc", "/openapi.json"}

# Prefijos de rutas internas de FastAPI/Swagger
PUBLIC_PREFIXES = ("/docs/", "/redoc/")


class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Middleware que protege la API limitando el acceso a orígenes permitidos.

    Estrategia de defensa en capas:
    1. Rutas públicas (health, docs) — siempre accesibles
    2. Si API_KEY configurada — acepta peticiones con header X-API-Key correcto
    3. Valida header Origin o Referer contra ALLOWED_ORIGINS
    4. Permite peticiones sin Origin desde localhost (desarrollo)
    5. Bloquea todo lo demás con 403
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Rutas públicas — siempre accesibles
        if path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIXES):
            return await call_next(request)

        # WebSocket — se valida por origen también
        # Si API_KEY está configurada, aceptar peticiones con la clave correcta
        if settings.API_KEY:
            api_key = request.headers.get("X-API-Key")
            if api_key == settings.API_KEY:
                return await call_next(request)

        # Obtener origen de la petición
        origin = request.headers.get("origin", "")
        referer = request.headers.get("referer", "")

        # Permitir desde localhost en desarrollo
        local_origins = {"http://localhost", "http://127.0.0.1"}
        if any(origin.startswith(lo) or referer.startswith(lo) for lo in local_origins):
            return await call_next(request)

        # Validar contra orígenes permitidos
        allowed = settings.ALLOWED_ORIGINS
        origin_ok = any(origin.startswith(a) for a in allowed) if origin else False
        referer_ok = any(referer.startswith(a) for a in allowed) if referer else False

        if origin_ok or referer_ok:
            return await call_next(request)

        # Sin origen (petición directa a la API — curl, Postman, scrapers)
        # Solo bloqueamos si no hay ningún indicador de origen legítimo
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