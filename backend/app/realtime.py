from __future__ import annotations

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.connections: dict[WebSocket, int] = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        self.connections[websocket] = user_id

    def disconnect(self, websocket: WebSocket):
        self.connections.pop(websocket, None)

    async def broadcast(
        self,
        event: str,
        data: dict,
        user_id: int | None = None,
    ):
        target_user_id = user_id if user_id is not None else data.get("user_id")
        if target_user_id is None:
            return

        dead: list[WebSocket] = []
        for connection, connection_user_id in list(self.connections.items()):
            if connection_user_id != target_user_id:
                continue
            try:
                await connection.send_json({
                    "event": event,
                    "data": data,
                })
            except Exception:
                dead.append(connection)

        for connection in dead:
            self.disconnect(connection)


manager = ConnectionManager()
