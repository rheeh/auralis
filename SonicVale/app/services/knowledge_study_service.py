from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.po import AdaptationRunPO, ChatSessionPO, KnowledgeReviewAnswerPO, LinePO


class KnowledgeStudyService:
    def __init__(self, db: Session):
        self.db = db

    def knowledge_points(self, session_id: str) -> list[dict[str, Any]]:
        session, run = self._context(session_id)
        points = [dict(item) for item in (run.article_analysis_json or {}).get("key_points", [])]
        line_map: dict[str, list[dict[str, Any]]] = {}
        if session.chapter_id:
            lines = self.db.execute(select(LinePO).where(LinePO.chapter_id == session.chapter_id).order_by(LinePO.line_order.asc())).scalars()
            for line in lines:
                metadata = line.knowledge_metadata or {}
                for point_id in metadata.get("knowledge_point_ids", []):
                    line_map.setdefault(point_id, []).append({
                        "line_id": line.id, "line_order": line.line_order, "segment_title": metadata.get("segment_title"),
                        "text": line.text_content, "audio_path": line.audio_path, "has_audio": bool(line.audio_path and line.status == "done"),
                    })
        for point in points:
            point["script_lines"] = line_map.get(point.get("id"), [])
        return points

    def review_questions(self, session_id: str) -> list[dict[str, Any]]:
        _, run = self._context(session_id)
        questions = [dict(item) for item in (run.final_json or run.draft_json or {}).get("review_questions", [])]
        answers = self.db.execute(select(KnowledgeReviewAnswerPO).where(
            KnowledgeReviewAnswerPO.session_id == session_id,
        ).order_by(KnowledgeReviewAnswerPO.created_at.asc())).scalars().all()
        answer_map: dict[str, list[dict[str, Any]]] = {}
        for row in answers:
            answer_map.setdefault(row.question_id, []).append({
                "id": row.id, "answer": row.answer, "matches_reference": row.matches_reference, "created_at": row.created_at,
            })
        for question in questions:
            question["attempts"] = answer_map.get(question.get("id"), [])
        return questions

    def answer_question(self, session_id: str, question_id: str, answer: str) -> dict[str, Any]:
        questions = self.review_questions(session_id)
        question = next((item for item in questions if item.get("id") == question_id), None)
        if not question:
            raise ValueError("复习问题不存在")
        normalized_answer = self._normalize_answer(answer)
        normalized_reference = self._normalize_answer(question.get("answer", ""))
        matches = normalized_answer == normalized_reference if normalized_answer and normalized_reference else False
        row = KnowledgeReviewAnswerPO(
            session_id=session_id, question_id=question_id, answer=answer.strip(), matches_reference=matches,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return {
            "id": row.id, "session_id": session_id, "question_id": question_id,
            "answer": row.answer, "matches_reference": row.matches_reference,
            "reference_answer": question.get("answer"), "source_excerpt": question.get("source_excerpt"),
            "note": "答案匹配仅用于文本参考，不代表已经掌握该知识点。",
            "created_at": row.created_at,
        }

    def _context(self, session_id: str) -> tuple[ChatSessionPO, AdaptationRunPO]:
        session = self.db.get(ChatSessionPO, session_id)
        if not session or session.deleted_at is not None or session.source_type != "knowledge_article":
            raise ValueError("知识文章会话不存在")
        run = self.db.get(AdaptationRunPO, session.adaptation_run_id) if session.adaptation_run_id else None
        if not run:
            raise ValueError("知识文章运行记录不存在")
        return session, run

    @staticmethod
    def _normalize_answer(value: str) -> str:
        return re.sub(r"[\W_]+", "", value or "", flags=re.UNICODE).casefold()
