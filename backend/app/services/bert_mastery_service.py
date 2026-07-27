"""
BERT Mastery 評估服務

使用 RoBERTa 模型評估學生的知識點掌握程度。
此模組可被 Preview 和 Review 階段共用。

掌握程度分級（3 級）：
- 待加強 (id=0)
- 尚可 (id=1)
- 精熟 (id=2)
"""

import os
import re
import torch
from typing import Dict, Optional, Tuple
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 模型路徑配置
# 使用絕對路徑，從 services 目錄往上找到專案根目錄
import pathlib
_SERVICES_DIR = pathlib.Path(__file__).parent  # backend/app/services
_PROJECT_ROOT = _SERVICES_DIR.parent.parent.parent  # services -> app -> backend -> Cook.ai
# 0228 model path
DEFAULT_MODEL_PATH = str(_PROJECT_ROOT / "models" / "bert_mastery" / "final_model")

# DEFAULT_MODEL_PATH = str(_PROJECT_ROOT / "models" / "bert_mastery" / "final_model_without_chatlog")
BERT_MODEL_PATH = os.getenv('BERT_MODEL_PATH', DEFAULT_MODEL_PATH)
BERT_DEVICE = os.getenv('BERT_DEVICE', None)

# Label 對應
MASTERY_LABELS = {0: "待加強", 1: "尚可", 2: "精熟"}


class BertMasteryService:
    """
    BERT Mastery 評估服務（Singleton 模式）
    
    使用 RoBERTa 模型評估學生的知識點掌握程度。
    """
    
    _instance: Optional['BertMasteryService'] = None
    _initialized: bool = False
    
    def __new__(cls) -> 'BertMasteryService':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.model_path = BERT_MODEL_PATH
        self.device = BERT_DEVICE or ('cuda' if torch.cuda.is_available() else 'cpu')
        self.tokenizer = None
        self.model = None
        self.max_len = 512
        self.label_map = MASTERY_LABELS
        self._initialized = True
        self._model_loaded = False
        
    def _load_model(self) -> bool:
        """
        延遲載入模型（第一次使用時載入）
        
        Returns:
            bool: 是否載入成功
        """
        if self._model_loaded:
            return True
            
        if not os.path.exists(self.model_path):
            print(f"⚠️  BERT 模型路徑不存在: {self.model_path}")
            print("   將使用 fallback 規則評估...")
            return False
        
        try:
            print(f"正在載入 BERT Mastery 模型: {self.model_path}")
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_path)
            self.model = AutoModelForSequenceClassification.from_pretrained(self.model_path)
            self.model.to(self.device)
            self.model.eval()
            self._model_loaded = True
            print(f"✅ BERT 模型載入成功 (device: {self.device})")
            return True
        except Exception as e:
            print(f"❌ BERT 模型載入失敗: {e}")
            return False
    

    def _format_input(self, sample: Dict) -> str:
        """
        格式化輸入文本，與訓練資料格式一致。
        
        Args:
            sample: 包含 chapter, section, Short_Answer_Log 的字典
            
        Returns:
            格式化後的輸入字串
        """
        chapter = str(sample.get('chapter', ''))
        section = str(sample.get('section', ''))
        # 不再清理學生表現標籤，保留原始作答記錄
        short_answer_log = str(sample.get('Short_Answer_Log', ''))
        
        formatted_text = (
            f"章節 : {chapter}\n"
            f"知識點 : {section}\n"
            f"學生掌握度 : [MASK]\n"
            f"簡答題作答紀錄 :\n{short_answer_log}\n"
        )
        return formatted_text
    
    def _fallback_predict(self, sample: Dict) -> Tuple[str, float, Dict[str, float]]:
        """
        Fallback 規則評估（當模型無法載入時使用）
        
        使用簡答題正確率來判定 Mastery 等級
        """
        short_answer_log = str(sample.get('Short_Answer_Log', ''))
        
        # 計算正確率
        correct_count = short_answer_log.lower().count('correct') - short_answer_log.lower().count('incorrect')
        incorrect_count = short_answer_log.lower().count('incorrect')
        partial_count = short_answer_log.lower().count('partially')
        total = max(correct_count + incorrect_count + partial_count, 1)
        
        accuracy = (correct_count + partial_count * 0.5) / total
        
        if accuracy >= 0.8:
            return "精熟", 0.7, {"待加強": 0.1, "尚可": 0.2, "精熟": 0.7}
        elif accuracy >= 0.5:
            return "尚可", 0.6, {"待加強": 0.2, "尚可": 0.6, "精熟": 0.2}
        else:
            return "待加強", 0.6, {"待加強": 0.6, "尚可": 0.3, "精熟": 0.1}
    
    def predict(self, sample: Dict) -> Dict:
        """
        評估學生的 Mastery 等級
        
        Args:
            sample: 包含以下欄位的字典：
                - chapter: 章節名稱
                - section: 知識點名稱
                - Short_Answer_Log: 簡答題作答記錄（包含學生表現標籤）
        
        Returns:
            Dict 包含:
                - prediction: 掌握程度（待加強/尚可/精熟）
                - prediction_id: 等級 ID (0/1/2)
                - confidence: 置信度分數
                - probabilities: 各等級的機率分布
        """
        # 嘗試載入模型
        if not self._load_model():
            # 使用 fallback
            prediction, confidence, probs = self._fallback_predict(sample)
            return {
                "prediction": prediction,
                "prediction_id": list(self.label_map.values()).index(prediction),
                "confidence": confidence,
                "probabilities": probs,
                "fallback": True
            }
        
        # 格式化輸入
        text = self._format_input(sample)
        
        # Tokenize
        encoding = self.tokenizer(
            text,
            add_special_tokens=True,
            max_length=self.max_len,
            padding="max_length",
            truncation=True,
            return_tensors="pt"
        )
        
        input_ids = encoding['input_ids'].to(self.device)
        attention_mask = encoding['attention_mask'].to(self.device)
        
        # 推論
        with torch.no_grad():
            outputs = self.model(input_ids=input_ids, attention_mask=attention_mask)
            logits = outputs.logits
            probs = torch.softmax(logits, dim=1).cpu().numpy()[0]
            pred_id = int(probs.argmax())
        
        return {
            "prediction": self.label_map[pred_id],
            "prediction_id": pred_id,
            "confidence": float(probs[pred_id]),
            "probabilities": {
                self.label_map[i]: float(probs[i]) for i in range(len(probs))
            },
            "fallback": False
        }


# 全域服務實例
_bert_service: Optional[BertMasteryService] = None


def get_bert_mastery_service() -> BertMasteryService:
    """
    獲取 BERT Mastery 服務實例（Singleton）
    """
    global _bert_service
    if _bert_service is None:
        _bert_service = BertMasteryService()
    return _bert_service

async def predict_mastery(
    chapter: str,
    section: str,
    short_answer_log: str
) -> Dict:
    """
    異步包裝函數：評估 Mastery 等級（使用本地 GPU）
    
    Returns:
        Dict 包含:
            - prediction: 掌握程度（待加強/尚可/精熟）
            - prediction_id: 等級 ID (0/1/2)
            - confidence: 置信度分數
            - probabilities: 各等級的機率分布
            - fallback: 是否使用 fallback 規則
            - bert_input: 實際傳給模型的格式化文字
    """
    service = get_bert_mastery_service()
    sample = {
        "chapter": chapter,
        "section": section,
        "Short_Answer_Log": short_answer_log
    }
    result = service.predict(sample)
    # 附上格式化輸入（即使 fallback 也記錄）
    result["bert_input"] = service._format_input(sample)
    return result
