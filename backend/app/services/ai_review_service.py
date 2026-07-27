"""
AI 回顧服務 - LIME 解釋 Agent

根據 LIME 報告的關鍵詞權重，生成自然語言解釋，
說明為什麼將學生的知識點掌握度判斷成某個等級。
"""

import os
from typing import Dict, List, Optional
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


class AIReviewService:
    """AI 回顧服務（Singleton）"""
    
    _instance: Optional['AIReviewService'] = None
    _initialized: bool = False
    
    def __new__(cls) -> 'AIReviewService':
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
            print(f"AI Review Service: 已啟用 (model: {self.openai_model})")
        else:
            self.openai_client = None
            self.enabled = False
            print("⚠️ AI Review Service: 未設定 OPENAI_API_KEY，已停用")
        
        self._initialized = True
    
    async def generate_lime_explanation(
        self,
        knowledge_point_name: str,
        mastery_level: str,
        confidence: float,
        feature_weights: Optional[List[Dict]] = None,
        lime_report_path: Optional[str] = None
    ) -> str:
        """
        根據 LIME 報告生成掌握度判斷的解釋
        
        Args:
            knowledge_point_name: 知識點名稱
            mastery_level: 掌握度等級 ("待加強" / "尚可" / "精熟")
            confidence: 信心度 (0.0 ~ 1.0)
            feature_weights: 特徵權重列表 [{keyword, weight}, ...]
            lime_report_path: LIME HTML 報告路徑 (會自動推導 .json 路徑)
        
        Returns:
            1-2 句話的自然語言解釋
        """
        if not self.enabled:
            return self._generate_fallback_explanation(
                knowledge_point_name, mastery_level, confidence, feature_weights or []
            )

        # 嘗試從檔案讀取
        if not feature_weights and lime_report_path:
            import json
            # 將 .html 換成 .json
            json_path = os.path.join("backend", lime_report_path.replace(".html", ".json"))
            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        json_data = json.load(f)
                        # 新格式: {"feature_weights": [...], "highlighted_text": {...}}
                        if "feature_weights" in json_data and isinstance(json_data["feature_weights"], list):
                            feature_weights = json_data["feature_weights"]
                        else:
                            # 舊格式: {keyword: weight} - 轉換成新格式
                            feature_weights = [{"keyword": k, "weight": v} for k, v in json_data.items() if isinstance(v, (int, float))]
                except Exception as e:
                    print(f"⚠️  讀取 LIME JSON 失敗: {e}")

        if not feature_weights:
            return f"根據系統分析，您在「{knowledge_point_name}」的掌握度目前評估為「{mastery_level}」。"

        # 分離正向與負向關鍵詞
        positive_keywords = [fw for fw in feature_weights if fw['weight'] > 0]
        negative_keywords = [fw for fw in feature_weights if fw['weight'] < 0]
        
        # 取前 3 個最重要的
        top_positive = [kw['keyword'] for kw in sorted(positive_keywords, key=lambda x: x['weight'], reverse=True)[:3]]
        top_negative = [kw['keyword'] for kw in sorted(negative_keywords, key=lambda x: x['weight'])[:3]]
        
        prompt = f"""你是一位親切、專業的 AI 學習分析師。請「解釋」這份 AI 診斷學習報告。針對學生在「{knowledge_point_name}」的當前表現（評估等級：{mastery_level}，信心度 {confidence:.0%}），撰寫一段 1-2 句話的中文解釋。
        
        數據參考：
        - 正向關鍵詞（支持此等級）：{', '.join(top_positive) if top_positive else '無'}
        - 負向關鍵詞（指出尚待加強處）：{', '.join(top_negative) if top_negative else '無'}
        
        撰寫指引：
        1. **自然口語**：像是一位老師在看著報表對學生說話，說明「為什麼 AI 會這樣判斷」。
        2. **結合證據**：自然地提到 1-2 個關鍵詞作為依據（例如：因為您的回答中準確運用了「...」）。
        3. **口氣溫柔**：即使是待加強，也要給予鼓勵。
        4. **禁止術語**：絕對不要使用「LIME」、「權重」、「信心度」、「正向/負向關鍵詞」等技術字眼。
        5. **長度**：回覆控制在 60 字以內。
        
        請直接輸出解釋文字，不需要任何標題。"""

        try:
            response = self.openai_client.chat.completions.create(
                model=self.openai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=150
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            print(f"⚠️ AI 回顧生成失敗: {e}")
            return self._generate_fallback_explanation(
                knowledge_point_name, mastery_level, confidence, feature_weights
            )
    async def generate_unit_review(
        self,
        unit_name: str,
        knowledge_points: List[Dict],
        stage: str = 'review'
    ) -> str:
        """
        生成單元整體學習回顧
        
        Args:
            unit_name: 單元名稱
            knowledge_points: 知識點列表，每個包含 mastery_level, name 等資訊
            stage: 階段 ('preview' 或 'review')
            
        Returns:
            一段自然語言的單元回顧
        """
        if not self.enabled:
            return "AI 服務暫時不可用，請稍後再試。"

        # 分析數據 (優先抓取該階段特定的掌握度欄位)
        total_kps = len(knowledge_points)
        
        if total_kps == 0:
            return f"歡迎來到「{unit_name}」單元！目前本單元尚未設定具體的知識點，建議你可以先瀏覽課程大綱，為接下來的學習做好準備。加油！"

        mastery_key = 'preview_mastery_level' if stage == 'preview' else 'review_mastery_level'
        
        def get_mastery(kp):
             return kp.get(mastery_key) or kp.get('mastery_level') or 'unknown'

        mastered_kps = [kp['name'] for kp in knowledge_points if get_mastery(kp) == '精熟']
        moderate_kps = [kp['name'] for kp in knowledge_points if get_mastery(kp) == '尚可']
        weak_kps = [kp['name'] for kp in knowledge_points if get_mastery(kp) == '待加強']
        
        mastered_count = len(mastered_kps)
        
        # 根據階段調整提示詞
        if stage == 'preview':
            context = "課前預習診斷"
            goal = "解釋 AI 如何根據學生的作答與對話分析其知識掌握狀態，並提供針對性的預習建議"
        else:
            context = "課後成效追蹤"
            goal = "根據診斷報告總結學習成果，解釋評分依據，並指出進步空間"

        # 準備診斷細節（如果有的話）
        diagnostic_details = []
        for kp in knowledge_points:
            name = kp['name']
            level = kp.get('mastery_level') or '待加強'
            # 嘗試獲取關鍵詞依據
            keywords = kp.get('top_positive', [])
            if keywords:
                diagnostic_details.append(f"- 【{name}】程度：{level}。關鍵證指出學生理解了「{', '.join(keywords)}」。")
            else:
                diagnostic_details.append(f"- 【{name}】程度：{level}。")

        diagnostic_info = "\n".join(diagnostic_details)

        prompt = f"""你是一位親切且極具專業洞察力的 AI 學習導師。請撰寫一份「{unit_name}」單元的「{context}」解釋報告。

當前學習狀態概況：
- 已精熟：{mastered_count} 個 ({', '.join(mastered_kps[:3])}{'...' if len(mastered_kps)>3 else ''})
- 待加強：{len(weak_kps)} 個 ({', '.join(weak_kps[:3])}{'...' if len(weak_kps)>3 else ''})

各知識點細節與診斷數據：
{diagnostic_info if diagnostic_info else "目前尚無具體證據關鍵詞，請根據程度等級進行概括性診斷。"}

撰寫要求：
1. **診斷與解釋**：你的任務是向學生「解釋」這份 AI 診斷報告。請說明為什麼 AI 會這樣判斷其目前的知識掌握度。
2. **自然口語**：像是一位老師在看著報表對學生親口解說。口吻要專業且充滿鼓勵。
3. **整合視角**：將各個知識點串聯成單元的整體學習觀狀態。
4. **禁止術語**：絕對禁止提到「LIME」、「權重」、「JSON」、「關鍵詞數據」、「標籤」等字眼。
5. **長度**：控制在 100-120 字左右，保持精簡但深刻。

目標：{goal}

請直接輸出診斷解釋內容。"""

        try:
            response = self.openai_client.chat.completions.create(
                model=self.openai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=200
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"⚠️ Unit Review 生成失敗: {e}")
            return f"本單元共有 {total_kps} 個知識點，你已精熟 {mastered_count} 個。繼續加油！"

        """當 LLM 不可用時的 fallback 解釋"""
        top_keywords = sorted(feature_weights, key=lambda x: abs(x['weight']), reverse=True)[:2]
        kw_text = '、'.join([kw['keyword'] for kw in top_keywords]) if top_keywords else '核心概念'
        
        if mastery_level == "精熟":
            return f"你在「{knowledge_point_name}」表現優秀，準確掌握了{kw_text}等核心概念！"
        elif mastery_level == "尚可":
            return f"你對「{knowledge_point_name}」有基本理解，建議加強{kw_text}的練習。"
        else:
            return f"「{knowledge_point_name}」尚需加強，建議複習{kw_text}相關內容。"


# 全域服務實例
_ai_review_service: Optional[AIReviewService] = None


def get_ai_review_service() -> AIReviewService:
    """獲取 AI Review 服務實例"""
    global _ai_review_service
    if _ai_review_service is None:
        _ai_review_service = AIReviewService()
    return _ai_review_service


async def generate_lime_explanation(
    knowledge_point_name: str,
    mastery_level: str,
    confidence: float,
    feature_weights: Optional[List[Dict]] = None,
    lime_report_path: Optional[str] = None
) -> str:
    """便捷函數：生成 LIME 解釋"""
    service = get_ai_review_service()
    return await service.generate_lime_explanation(
        knowledge_point_name, mastery_level, confidence, feature_weights, lime_report_path
    )

async def generate_unit_review(
    unit_name: str,
    knowledge_points: List[Dict],
    stage: str = 'review'
) -> str:
    """便捷函數：生成單元整體回顧"""
    service = get_ai_review_service()
    return await service.generate_unit_review(
        unit_name, knowledge_points, stage
    )
