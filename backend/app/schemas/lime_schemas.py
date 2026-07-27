"""
LIME 報告 Schema 定義

用於回傳 LIME 可解釋性分析的 JSON 格式資料，供前端渲染使用。
掌握度預測結果已存於資料庫，此 API 僅回傳關鍵詞分析。
"""

from pydantic import BaseModel
from typing import List, Optional


class FeatureWeight(BaseModel):
    """特徵（關鍵詞）權重"""
    keyword: str
    weight: float  # 正值：支持預測（綠色），負值：反對預測（紅色）


class TextHighlight(BaseModel):
    """文本高亮標記"""
    start: int
    end: int
    keyword: str
    weight: float


class HighlightedText(BaseModel):
    """高亮文本（含原文與高亮位置）"""
    original: str
    highlights: List[TextHighlight]


class LimeReportResponse(BaseModel):
    """LIME 報告回應（簡化版）"""
    knowledge_point_id: int
    knowledge_point_name: str
    stage: str  # "preview" / "review"
    
    # 核心資料
    feature_weights: List[FeatureWeight]  # 特徵重要性（按權重絕對值排序）
    highlighted_text: Optional[HighlightedText] = None  # 原始文本（關鍵詞高亮）
    
    generated_at: str  # ISO 8601 格式


class LimeSummary(BaseModel):
    """LIME 報告摘要（用於 Dashboard）"""
    top_keywords: List[str]  # 前 3 個重要關鍵詞（按權重絕對值）
    lime_report_url: str  # e.g., "/api/v1/student/kps/123/lime-report?stage=preview"

