from typing import Dict, Optional
from backend.app.config.settings import settings

def calculate_adaptive_top_k(
    num_documents: int,
    knowledge_point_counts: Optional[Dict[int, int]] = None,  # {doc_id: kp_count}
    base_per_doc: int = 4
) -> int:
    """
    動態計算總 top_k
    策略：保底 10 (from settings)，上限 20，隨文檔數微幅增加
    
    Args:
        num_documents: 文檔總數
        knowledge_point_counts: (暫未深入使用) 教師勾選的 KP 分布
        base_per_doc: (已棄用，改用 settings 基準)
    
    Returns:
        total_top_k: 總檢索數量
    """
    if num_documents == 0:
        return 0

    # 1. 取得基準值 (Default: 10)
    base_k = settings.rag.top_k
    
    # 2. 計算動態值：確保每個文檔至少有 2 個 quota，但總數不低於 base_k
    # 例如：1 doc -> max(10, 2) = 10
    #      6 docs -> max(10, 12) = 12
    calculated_k = max(base_k, num_documents * 2)
    
    # 3. 設定絕對上限 (Cap)，避免 Context Window 爆炸
    MAX_K_CAP = 20
    
    final_k = min(calculated_k, MAX_K_CAP)
    
    return final_k
