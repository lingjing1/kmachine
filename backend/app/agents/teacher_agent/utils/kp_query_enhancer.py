"""
KP Query Enhancer - 自然中文融合版本

將 KP 自然地融入 user prompt，產生更符合中文語法的增強查詢。
"""

from typing import List, Optional
import re


class KPQueryEnhancer:
    """
    KP Query 增強器
    
    根據不同的 prompt 類型，智能地將 KP 融入查詢，產生自然的中文句子。
    """
    
    @staticmethod
    def enhance(user_prompt: str, kp_names: Optional[List[str]]) -> str:
        """
        主要增強方法
        
        Args:
            user_prompt: 原始用戶查詢
            kp_names: 選定的知識點名稱列表
            
        Returns:
            增強後的查詢字串
            
        Examples:
            >>> enhance("生成 10 題選擇題", ["梯度下降", "反向傳播"])
            "生成關於梯度下降、反向傳播的 10 題選擇題"
            
            >>> enhance("幫我總結教材", ["智能代理架構", "記憶系統"])
            "幫我總結教材（聚焦於智能代理架構、記憶系統）"
        """
        if not kp_names:
            return user_prompt
        
        # 使用頓號連接 KP（更符合中文習慣）
        kp_context = "、".join(kp_names)
        
        # 策略 1: 處理「生成 X 題」類型
        if re.search(r'生成.*題', user_prompt):
            return KPQueryEnhancer._enhance_generation_query(user_prompt, kp_context)
        
        # 策略 2: 處理「總結」「摘要」類型
        elif any(keyword in user_prompt for keyword in ['總結', '摘要', '整理']):
            return KPQueryEnhancer._enhance_summary_query(user_prompt, kp_context)
        
        # 策略 3: 處理「解釋」「說明」類型
        elif any(keyword in user_prompt for keyword in ['解釋', '說明', '講解']):
            return KPQueryEnhancer._enhance_explanation_query(user_prompt, kp_context)
        
        # Fallback: 簡單拼接
        else:
            return f"{user_prompt} 關於 {kp_context}"
    
    @staticmethod
    def _enhance_generation_query(prompt: str, kp_context: str) -> str:
        """
        增強「生成題目」類型的查詢
        
        Examples:
            "生成 10 題選擇題" → "生成關於梯度下降、反向傳播的 10 題選擇題"
            "產生簡答題" → "產生關於深度學習的簡答題"
        """
        # 嘗試在「生成」後插入「關於 KP 的」
        if '生成' in prompt:
            enhanced = prompt.replace('生成', f'生成關於{kp_context}的', 1)
            return enhanced
        elif '產生' in prompt:
            enhanced = prompt.replace('產生', f'產生關於{kp_context}的', 1)
            return enhanced
        else:
            return f"{prompt}，主題為 {kp_context}"
    
    @staticmethod
    def _enhance_summary_query(prompt: str, kp_context: str) -> str:
        """
        增強「總結/摘要」類型的查詢
        
        Examples:
            "幫我總結教材" → "幫我總結教材（聚焦於智能代理架構、記憶系統）"
            "整理重點" → "整理重點（聚焦於梯度下降、反向傳播）"
        """
        # 使用括號附加 KP 上下文
        return f"{prompt.rstrip()}（聚焦於{kp_context}）"
    
    @staticmethod
    def _enhance_explanation_query(prompt: str, kp_context: str) -> str:
        """
        增強「解釋/說明」類型的查詢
        
        Examples:
            "請解釋這個概念" → "請解釋梯度下降、反向傳播這些概念"
            "說明原理" → "說明梯度下降、反向傳播的原理"
        """
        # 嘗試在關鍵詞前插入 KP
        for keyword in ['概念', '原理', '方法', '技術']:
            if keyword in prompt:
                enhanced = prompt.replace(keyword, f'{kp_context}的{keyword}', 1)
                return enhanced
        
        # Fallback
        return f"{prompt}，聚焦於 {kp_context}"


# 便捷函數
def enhance_query_with_kp(user_prompt: str, kp_names: Optional[List[str]] = None) -> str:
    """
    便捷的增強函數
    
    Args:
        user_prompt: 原始查詢
        kp_names: KP 名稱列表
        
    Returns:
        增強後的查詢
    """
    return KPQueryEnhancer.enhance(user_prompt, kp_names)
