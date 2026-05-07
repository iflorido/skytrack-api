# ── Stage 1: Builder ─────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Dependencias del sistema para compilar asyncpg y cryptography
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Runtime ─────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Dependencias de runtime (solo libpq para asyncpg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar paquetes instalados del builder
COPY --from=builder /install /usr/local

# Crear directorio de logs
RUN mkdir -p /app/logs

# Copiar código fuente
COPY . .

# Usuario no-root por seguridad
RUN useradd --no-create-home --shell /bin/false skytrack && \
    chown -R skytrack:skytrack /app
USER skytrack

# Variables de entorno con valores por defecto (sin secretos)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    ENVIRONMENT=production \
    DEBUG=false \
    DB_HOST=host.docker.internal \
    DB_PORT=5432 \
    DB_NAME=admin_skytrack_db \
    DB_USER=admin_userflyskytrack \
    POLL_INTERVAL_SECONDS=10 \
    WS_HEARTBEAT_INTERVAL=30

# Puerto de la API
EXPOSE 8064

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8064/health || exit 1

# Arranque con uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8064", \
     "--workers", "1", "--loop", "uvloop", "--http", "h11", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]