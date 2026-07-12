import asyncio
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class WSManager:
    """Keeps legacy sockets working while isolating new workflow sessions."""

    def __init__(self):
        self._legacy: dict[WebSocket, int | None] = {}
        self._sessions: dict[int, dict[str, set[WebSocket]]] = defaultdict(lambda: defaultdict(set))
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def conns(self) -> list[WebSocket]:
        return list(self._legacy)

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, ws: WebSocket, project_id: int | None = None):
        await ws.accept()
        self._legacy[ws] = project_id

    async def connect_session(self, ws: WebSocket, project_id: int, session_id: str):
        await ws.accept()
        self._sessions[project_id][session_id].add(ws)

    def disconnect(self, ws: WebSocket):
        self._legacy.pop(ws, None)
        for project_id, sessions in list(self._sessions.items()):
            for session_id, sockets in list(sessions.items()):
                sockets.discard(ws)
                if not sockets:
                    sessions.pop(session_id, None)
            if not sessions:
                self._sessions.pop(project_id, None)

    async def _send_many(self, sockets: list[WebSocket], data: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in sockets:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def broadcast(self, data: dict[str, Any]):
        """Compatibility broadcast. Project-tagged events stay within that project."""
        project_id = data.get("project_id")
        sockets = [
            ws
            for ws, subscribed_project in self._legacy.items()
            if project_id is None or subscribed_project is None or subscribed_project == project_id
        ]
        await self._send_many(sockets, data)

    async def broadcast_project(self, project_id: int, data: dict[str, Any]):
        sockets = [ws for ws, subscribed_project in self._legacy.items() if subscribed_project in {None, project_id}]
        await self._send_many(sockets, data)

    async def broadcast_session(self, project_id: int, session_id: str, data: dict[str, Any]):
        sockets = list(self._sessions.get(project_id, {}).get(session_id, set()))
        await self._send_many(sockets, data)

    def publish_from_worker(self, project_id: int, session_id: str, data: dict[str, Any]) -> None:
        """Best-effort bridge for synchronous LangGraph nodes running in a worker thread."""
        if not self._loop or self._loop.is_closed():
            return
        try:
            asyncio.run_coroutine_threadsafe(self.broadcast_session(project_id, session_id, data), self._loop)
            asyncio.run_coroutine_threadsafe(self.broadcast_project(project_id, data), self._loop)
        except Exception:
            logging.exception("发布工作流 WebSocket 事件失败")


manager = WSManager()
