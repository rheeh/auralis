from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session
from sqlalchemy import update, func

from app.core.ws_manager import manager
from app.models.po import ChatSessionPO, WorkflowEventPO


class WorkflowEventPublisher:
    def __init__(self, db: Session):
        self.db = db

    def publish(self, session: ChatSessionPO, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self.db.flush()  # include the caller's stage/checkpoint in this transaction
        sequence=self.db.execute(update(ChatSessionPO).where(ChatSessionPO.id==session.id)
            .values(last_event_sequence=func.coalesce(ChatSessionPO.last_event_sequence,0)+1)
            .returning(ChatSessionPO.last_event_sequence),execution_options={'synchronize_session':False}).scalar_one()
        event = WorkflowEventPO(
            id=f"evt_{uuid4().hex}",
            session_id=session.id,
            project_id=session.project_id,
            sequence=sequence,
            event_type=event_type,
            stage=session.current_stage,
            payload_json=payload or {},
        )
        self.db.add(event)
        self.db.commit()
        data = {
            "event_id": event.id,
            "event_type": event.event_type,
            "session_id": session.id,
            "project_id": session.project_id,
            "sequence": event.sequence,
            "stage": event.stage,
            "payload": event.payload_json or {},
            "created_at": (event.created_at or datetime.now(timezone.utc)).isoformat(),
        }
        try:
            manager.publish_from_worker(session.project_id, session.id, data)
        except Exception:
            import logging
            logging.warning("事件已保存但通知失败: %s",event.id)
        return data
