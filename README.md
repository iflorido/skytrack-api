# SkyTrack API

API en tiempo real para rastreo de aeronaves usando datos de [OpenSky Network](https://opensky-network.org).

## Stack

- **FastAPI** — framework async
- **PostgreSQL 16 + TimescaleDB** — base de datos de series temporales
- **asyncpg** — driver async para PostgreSQL
- **APScheduler / asyncio** — polling cada 10s
- **WebSockets** — push de datos al frontend
- **Docker** — contenedor de producción

## Estructura

```
backend/
├── main.py                          # Punto de entrada FastAPI
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── app/
    ├── core/
    │   ├── config.py                # Variables de entorno y settings
    │   ├── database.py              # Engine async + init TimescaleDB
    │   └── logging.py              # Loguru setup
    ├── models/
    │   └── models.py               # Tablas SQLAlchemy
    ├── schemas/
    │   └── schemas.py              # Pydantic schemas
    ├── services/
    │   ├── opensky_client.py       # Cliente OpenSky con OAuth2
    │   ├── websocket_manager.py    # Gestión de conexiones WS
    │   └── poller.py              # Servicio de polling
    └── routers/
        ├── states.py              # /api/v1/states/*
        ├── flights.py             # /api/v1/flights/*
        ├── tracks.py              # /api/v1/tracks/*
        └── health.py              # /health + /metrics
```

## Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| WS | `/api/v1/states/live` | Stream en tiempo real (~10.000 aeronaves cada 10s) |
| GET | `/api/v1/states/current` | Snapshot actual con filtros opcionales |
| GET | `/api/v1/states/aircraft/{icao24}` | Estado de una aeronave |
| GET | `/api/v1/states/stats` | Estadísticas globales |
| GET | `/api/v1/states/bbox` | Aeronaves en un área geográfica |
| GET | `/api/v1/flights/interval` | Vuelos en intervalo de tiempo |
| GET | `/api/v1/flights/aircraft/{icao24}` | Historial de una aeronave |
| GET | `/api/v1/flights/arrivals/{airport}` | Llegadas a un aeropuerto |
| GET | `/api/v1/flights/departures/{airport}` | Salidas de un aeropuerto |
| GET | `/api/v1/tracks/{icao24}` | Trayectoria de una aeronave |
| GET | `/health` | Estado del sistema |
| GET | `/metrics` | Métricas internas |
| GET | `/docs` | Swagger UI |

## Despliegue en VPS con Docker

### 1. Construir la imagen

```bash
docker build -t skytrack-api:latest .
```

### 2. Ejecutar el contenedor

```bash
docker run -d \
  --name skytrack-api \
  --restart unless-stopped \
  -p 8000:8000 \
  --add-host=host.docker.internal:host-gateway \
  -e DB_PASSWORD="tu_password" \
  -e DB_HOST="172.17.0.1" \
  -e OPENSKY_CLIENT_ID="tu_client_id" \
  -e OPENSKY_CLIENT_SECRET="tu_client_secret" \
  -v skytrack_logs:/app/logs \
  skytrack-api:latest
```

> **Nota sobre DB_HOST**: En Linux, el contenedor accede al PostgreSQL del host
> usando la IP del bridge de Docker. Comprueba con `ip addr show docker0`.
> Normalmente es `172.17.0.1`.

### 3. Nginx como reverse proxy (en el VPS)

```nginx
server {
    listen 443 ssl;
    server_name api.flyskytrack.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket support
    location /api/v1/states/live {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }
}
```

## Variables de entorno

| Variable | Por defecto | Descripción |
|----------|-------------|-------------|
| `DB_HOST` | `127.0.0.1` | Host de PostgreSQL |
| `DB_PORT` | `5432` | Puerto de PostgreSQL |
| `DB_NAME` | `admin_skytrack_db` | Nombre de la BD |
| `DB_USER` | `admin_userflyskytrack` | Usuario de la BD |
| `DB_PASSWORD` | **requerido** | Contraseña de la BD |
| `OPENSKY_CLIENT_ID` | `None` | OAuth2 client_id (opcional) |
| `OPENSKY_CLIENT_SECRET` | `None` | OAuth2 client_secret (opcional) |
| `POLL_INTERVAL_SECONDS` | `10` | Frecuencia de polling |
| `DEBUG` | `false` | Modo debug |

## Desarrollo local

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Crear .env local (nunca subir al repo)
echo "DB_PASSWORD=tu_password" > .env

uvicorn main:app --reload --port 8000
```