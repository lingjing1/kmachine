"""
Mastery Cache

使用 TTLCache 實作對話級別的精熟度快取。
同一個對話期間不需要重複查詢 DB。

快取策略：
- Key: (student_id, course_id, conversation_id)
- TTL: 30 分鐘
- 容量: 50,000 筆

注意：
- 單 worker 模式下有效
- 多 worker 需改用 Redis
"""

from cachetools import TTLCache
from threading import RLock
from typing import Any, Dict, List, Optional, Tuple, Union

# 快取設定
_cache: TTLCache = TTLCache(maxsize=50000, ttl=60 * 30)  # 30 分鐘 TTL
_lock = RLock()

# Key 類型: (student_id, course_id, conversation_id)
CacheKey = Tuple[int, int, str]


def get_mastery(
    student_id: int, 
    course_id: int, 
    conversation_id: str,
    knowledge_point_id: Optional[int] = None  # 保留參數相容性，不再使用
) -> Optional[Dict[str, Any]]:
    """從快取取得精熟度資料
    
    Args:
        student_id: 學生 ID
        course_id: 課程 ID
        conversation_id: 對話 ID
        knowledge_point_id: (已廢棄) 保留以維持向後相容，不影響 key

    Returns:
        快取的精熟度資料，若無則返回 None
    """
    key: CacheKey = (student_id, course_id, conversation_id)
    with _lock:
        return _cache.get(key)


def set_mastery(
    student_id: int, 
    course_id: int, 
    conversation_id: str,
    mastery_ctx: Dict[str, Any],
    knowledge_point_id: Optional[int] = None  # 保留參數相容性，不再使用
) -> None:
    """設定精熟度快取
    
    Args:
        student_id: 學生 ID
        course_id: 課程 ID
        conversation_id: 對話 ID
        mastery_ctx: 精熟度資料，包含 current_mastery (List[Dict]) 和 weak_points (List[str])
        knowledge_point_id: (已廢棄) 保留以維持向後相容，不影響 key
    """
    key: CacheKey = (student_id, course_id, conversation_id)
    with _lock:
        _cache[key] = mastery_ctx


def delete_mastery(
    student_id: int, 
    course_id: int, 
    conversation_id: str,
    knowledge_point_id: Optional[int] = None  # 保留參數相容性
) -> None:
    """刪除精熟度快取（用於對話刪除時）
    
    Args:
        student_id: 學生 ID
        course_id: 課程 ID
        conversation_id: 對話 ID
        knowledge_point_id: (已廢棄) 保留以維持向後相容
    """
    key: CacheKey = (student_id, course_id, conversation_id)
    with _lock:
        _cache.pop(key, None)


def clear_all() -> None:
    """清空所有快取（用於測試）"""
    with _lock:
        _cache.clear()
