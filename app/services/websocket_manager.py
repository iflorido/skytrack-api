import asyncio
import json
from typing import Optional
from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger
from app.schemas.schemas import LiveStateResponse


class ConnectionManager:
    """
    Gestiona todas las conexiones WebSocket activas.
    Hace broadcast del estado live a todos los clientes conectados.
    """

    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self._last_payload: Optional[str] = None   # cachea el último estado para nuevos clientes
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        logger.info(
            f"WebSocket conectado: {websocket.client} "
            f"— total: {len(self.active_connections)}"
        )
        # Enviar último estado conocido inmediatamente al conectarse
        if self._last_payload:
            try:
                await websocket.send_text(self._last_payload)
            except Exception:
                pass

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        logger.info(
            f"WebSocket desconectado: {websocket.client} "
            f"— total: {len(self.active_connections)}"
        )

    async def broadcast(self, data: LiveStateResponse):
        """Envía el estado actual a todos los clientes conectados."""
        if not self.active_connections:
            return

        payload = data.model_dump_json()
        self._last_payload = payload

        disconnected = []
        async with self._lock:
            connections = list(self.active_connections)

        for websocket in connections:
            try:
                await websocket.send_text(payload)
            except (WebSocketDisconnect, RuntimeError, Exception) as e:
                logger.debug(f"Cliente desconectado durante broadcast: {e}")
                disconnected.append(websocket)

        # Limpiar desconectados
        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    if ws in self.active_connections:
                        self.active_connections.remove(ws)

    async def send_to(self, websocket: WebSocket, data: dict):
        """Envía un mensaje a un cliente específico."""
        try:
            await websocket.send_text(json.dumps(data))
        except Exception as e:
            logger.debug(f"Error enviando mensaje individual: {e}")

    async def broadcast_ping(self):
        """Heartbeat para mantener conexiones vivas."""
        if not self.active_connections:
            return

        ping_msg = json.dumps({"type": "ping", "timestamp": __import__("time").time()})
        disconnected = []

        async with self._lock:
            connections = list(self.active_connections)

        for websocket in connections:
            try:
                await websocket.send_text(ping_msg)
            except Exception:
                disconnected.append(websocket)

        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    if ws in self.active_connections:
                        self.active_connections.remove(ws)

    @property
    def connection_count(self) -> int:
        return len(self.active_connections)


# Instancia global compartida
ws_manager = ConnectionManager()