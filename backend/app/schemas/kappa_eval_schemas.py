"""
教師 Kappa 評估 Schema 定義

四任務：
- course62_mastery       (Task A)  RoBERTa 掌握度 vs 教師
- course62_polarity      (Task B)  LIME 關鍵字極性 vs 教師
- finetune_mastery       (Task C1) CSV Mastery_Label vs 教師
- finetune_performance   (Task C2) CSV 學生表現 vs 教師
"""
from typing import List, Optional

from pydantic import BaseModel


# ---------- Overview / Dashboard ----------
class TaskProgress(BaseModel):
    task: str                       # 'course62_mastery' | ... | 'finetune_performance'
    total: int
    completed: int


class OverviewResponse(BaseModel):
    teacher_id: int
    tasks: List[TaskProgress]


# ---------- 清單（所有任務共用） ----------
class SampleListItem(BaseModel):
    id: int
    display_order: int
    stratum: str
    is_completed: bool
    submitted_at: Optional[str] = None


class SampleListResponse(BaseModel):
    task: str
    total: int
    completed: int
    items: List[SampleListItem]


# ---------- Task A: course62 mastery ----------
class Course62MasterySample(BaseModel):
    id: int
    display_order: int
    stratum: str
    ai_mastery: str
    ai_mastery_confidence: Optional[float]
    lime_report_json: dict
    teacher_mastery: Optional[str]
    teacher_note: Optional[str]
    submitted_at: Optional[str]


class Course62MasterySubmit(BaseModel):
    teacher_mastery: str            # 待加強 / 尚可 / 精熟
    teacher_note: Optional[str] = None


# ---------- Task B: course62 polarity ----------
class PolarityItem(BaseModel):
    keyword: str
    weight: float
    polarity: str                   # '+' or '-'
    is_meta: bool


class TeacherPolarityItem(BaseModel):
    keyword: str
    polarity: str                   # '+' or '-'


class Course62PolaritySample(BaseModel):
    id: int
    display_order: int
    stratum: str
    lime_report_json: dict
    ai_polarities: List[PolarityItem]
    teacher_polarities: Optional[List[TeacherPolarityItem]]
    teacher_note: Optional[str]
    submitted_at: Optional[str]


class Course62PolaritySubmit(BaseModel):
    teacher_polarities: List[TeacherPolarityItem]
    teacher_note: Optional[str] = None


# ---------- Task C1: finetune mastery ----------
class FinetuneMasterySample(BaseModel):
    id: int
    display_order: int
    stratum: str
    csv_row: dict
    ai_mastery: str
    teacher_mastery: Optional[str]
    teacher_note: Optional[str]
    submitted_at: Optional[str]


class FinetuneMasterySubmit(BaseModel):
    teacher_mastery: str
    teacher_note: Optional[str] = None


# ---------- Task C2: finetune performance ----------
class FinetunePerformanceSample(BaseModel):
    id: int
    display_order: int
    stratum: str
    question_snapshot: dict
    ai_performance: str
    teacher_performance: Optional[str]
    teacher_note: Optional[str]
    submitted_at: Optional[str]


class FinetunePerformanceSubmit(BaseModel):
    teacher_performance: str
    teacher_note: Optional[str] = None
