"""
課堂聆聽重點生成服務

根據學生在整個章節的知識點掌握度與作答記錄，
生成具體的課堂聆聽建議。
"""

import os
from typing import Dict, List, Optional
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


class ListeningHighlightsService:
    """課堂聆聽重點服務（Singleton）"""
    
    _instance: Optional['ListeningHighlightsService'] = None
    _initialized: bool = False
    
    def __new__(cls) -> 'ListeningHighlightsService':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            self.openai_client = OpenAI(api_key=api_key)
            self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            self.enabled = True
            print(f"Listening Highlights Service: 已啟用 (model: {self.openai_model})")
        else:
            self.openai_client = None
            self.enabled = False
            print("⚠️ Listening Highlights Service: 未設定 OPENAI_API_KEY，已停用")
        
        self._initialized = True
    
    async def generate_listening_highlights(
        self,
        unit_name: str,
        knowledge_points: List[Dict],
        stage: str = 'preview'
    ) -> List[str]:
        """
        根據章節知識點掌握狀況生成課堂聆聽建議
        
        Args:
            unit_name: 章節名稱
            knowledge_points: 知識點列表
            stage: 階段 ('preview' 或 'review')
        
        Returns:
            2-3 條課堂聆聽建議
        """
        if not knowledge_points:
            return [
                f"留意「{unit_name}」單元的核心學習目標。",
                "關注章節中提到的案例分析與實例。",
                "思考本單元內容如何應用於實際問題中。"
            ]

        if not self.enabled:
            return self._generate_fallback_highlights(unit_name, knowledge_points)
        
        # 分析知識點狀況
        weak_kps = [kp['name'] for kp in knowledge_points if kp.get('mastery_level') == '待加強']
        moderate_kps = [kp['name'] for kp in knowledge_points if kp.get('mastery_level') == '尚可']
        
        # 找出精熟但信心度低的知識點（需要鞏固）
        unstable_kps = [
            kp['name'] for kp in knowledge_points 
            if kp.get('mastery_level') == '精熟' and kp.get('confidence', 1.0) < 0.5
        ]

        if stage == 'preview':
            role_desc = "課前預習指導"
            action_verb = "預習時請留意"
            focus_type = "核心概念"
        else:
            role_desc = "課後複習教練"
            action_verb = "複習時請加強"
            focus_type = "實作細節與應用"
        
        prompt = f"""你是一位{role_desc}。根據學生在「{unit_name}」單元的狀態，生成 3 條具體的{action_verb}重點。

學生狀態：
- 待加強（優先）：{', '.join(weak_kps) if weak_kps else '無'}
- 信心不足（需鞏固）：{', '.join(unstable_kps) if unstable_kps else '無'}
- 尚可：{', '.join(moderate_kps) if moderate_kps else '無'}

要求：
1. 輸出一個 JSON 字串陣列 (Array of Strings)。
2. 每條建議不超過 25 字。
3. 針對{focus_type}，具體指出要聽什麼、看什麼。
4. **不要**有編號前綴。

範例：
["留意「決策樹」的分裂標準選擇。", "釐清「過度擬合」的發生原因。", "關注「剪枝」技術的實際應用。"]

只輸出 JSON，不要 Markdown 代碼塊。"""

        try:
            response = self.openai_client.chat.completions.create(
                model=self.openai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=300
            )
            
            import json
            import re
            
            content = response.choices[0].message.content.strip()
            
            # 移除 Markdown code block 標記 (如果有的話)
            content = re.sub(r'^```json\s*', '', content)
            content = re.sub(r'^```\s*', '', content)
            content = re.sub(r'\s*```$', '', content)

            # 解析 JSON
            try:
                highlights = json.loads(content)
            except json.JSONDecodeError:
                # 嘗試尋找陣列部分
                match = re.search(r'\[.*?\]', content, re.DOTALL)
                if match:
                    highlights = json.loads(match.group())
                else:
                    return self._generate_fallback_highlights(unit_name, knowledge_points)
            
            # 確保是 list 且元素是字串
            if isinstance(highlights, list) and all(isinstance(i, str) for i in highlights):
                return highlights[:3]
            else:
                 return self._generate_fallback_highlights(unit_name, knowledge_points)
            
        except Exception as e:
            print(f"⚠️ 課堂聆聽重點生成失敗: {e}")
            return self._generate_fallback_highlights(unit_name, knowledge_points)
    
    def _generate_fallback_highlights(
        self,
        unit_name: str,
        knowledge_points: List[Dict]
    ) -> List[str]:
        """當 LLM 不可用時的 fallback 建議"""
        highlights = []
        
        weak_kps = [kp['name'] for kp in knowledge_points if kp.get('mastery_level') == '待加強']
        moderate_kps = [kp['name'] for kp in knowledge_points if kp.get('mastery_level') == '尚可']
        
        if weak_kps:
            highlights.append(f"重點聆聽「{weak_kps[0]}」的核心概念說明。")
        if moderate_kps:
            highlights.append(f"注意「{moderate_kps[0]}」的進階應用範例。")
        if not highlights:
            highlights.append(f"複習「{unit_name}」的整體架構與概念連結。")
        
        return highlights[:3]


# 全域服務實例
_listening_service: Optional[ListeningHighlightsService] = None


def get_listening_highlights_service() -> ListeningHighlightsService:
    """獲取課堂聆聽重點服務實例"""
    global _listening_service
    if _listening_service is None:
        _listening_service = ListeningHighlightsService()
    return _listening_service


async def generate_listening_highlights(
    unit_name: str,
    knowledge_points: List[Dict],
    stage: str = 'preview'
) -> List[str]:
    """便捷函數：生成課堂聆聽建議"""
    service = get_listening_highlights_service()
    return await service.generate_listening_highlights(unit_name, knowledge_points, stage)
