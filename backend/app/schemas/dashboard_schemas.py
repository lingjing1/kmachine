from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from backend.app.schemas.lime_schemas import LimeSummary

class StudentAnswer(BaseModel):
    question_id: int
    answer: str
    answered_at: datetime

class KnowledgePointStatus(BaseModel):
    knowledge_point_id: int
    name: str
    mastery_level: str
    recent_answers: List[StudentAnswer] = []
    lime_summary: Optional[LimeSummary] = None  # LIME 報告摘要

class DashboardResponse(BaseModel):
    course_id: int
    unit_id: int
    knowledge_points: List[KnowledgePointStatus]
    ai_review: str
    listening_highlights: List[str]
