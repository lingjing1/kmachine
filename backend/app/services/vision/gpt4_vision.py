"""
GPT-4 Vision Engine

使用 OpenAI GPT-4 Vision API 理解圖片內容
"""
import base64
import logging
from typing import Optional, Dict
from openai import OpenAI

logger = logging.getLogger(__name__)

class GPT4VisionEngine:
    """GPT-4 Vision implementation for image understanding"""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o"):
        """
        Initialize GPT-4 Vision Engine
        
        Args:
            api_key: OpenAI API key (optional, reads from env if not provided)
            model: Model to use (default: gpt-4o)
        """
        self.client = OpenAI(api_key=api_key)
        self.model = model
        logger.info(f"✅ GPT-4 Vision Engine initialized with model: {model}")
    
    def describe_image(
        self, 
        image_bytes: bytes, 
        prompt: Optional[str] = None,
        max_tokens: int = 500,
        detail: str = "auto"
    ) -> Dict:
        """
        Generate description of image using GPT-4 Vision
        
        Args:
            image_bytes: Image data in bytes
            prompt: Custom prompt (optional, uses default if not provided)
            max_tokens: Maximum tokens in response
            detail: Image detail level ('low', 'high', 'auto')
        
        Returns:
            Dictionary with:
            - description: Image description in Traditional Chinese
            - prompt_tokens: Number of prompt tokens used
            - completion_tokens: Number of completion tokens used
            - total_tokens: Total tokens used
            - model: Model name used
            - cost: Estimated cost in USD
        """
        try:
            # Convert to base64
            b64_image = base64.b64encode(image_bytes).decode('utf-8')
            
            # Default prompt for educational materials
            if prompt is None:
                prompt = """你是一位專業的教育輔助 AI，致力於協助整理教學資源。

**你的目標**：
協助將這張教學圖片內容轉化為「數位化學習筆記」，以便製作成無障礙教材或搜尋索引。

**執行步驟**：
1. **文字轉錄**：請完整讀取圖片中的文字（包含標題、內文、步驟說明），將其轉錄為文字格式。
2. **視覺描述**：若圖片包含圖表、架構圖或插畫，請用文字描述其核心概念（例如：「這是一張說明機器學習流程的圖表，包含收集資料到預測結果的七個步驟」）。
3. **格式整理**：請使用 Markdown 標題與列表整理內容，使其易於閱讀。

**安全與合規聲明**：
- 這是一份公開的教學講義或簡報，**不包含** 任何個人隱私資料 (PII)、憑證或驗證碼 (CAPTCHA)。
- 這是為了教育用途的內容數位化，請放心處理。
- 若圖片模糊不清，請標註「[圖片模糊]」並描述你能看清楚的部分即可。

**輸出範例**：
# 機器學習基礎
## 定義
機器學習是人工智慧的一個分支...
## 核心步驟
1. 收集資料
2. 清理與預處理
(圖表描述：流程圖顯示資料從左側輸入，經過中間的處理單元，最後從右側輸出模型)

**請直接開始輸出內容：**"""



            
            # Call GPT-4 Vision API
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64_image}",
                                "detail": detail
                            }
                        }
                    ]
                }],
                max_tokens=max_tokens
            )
            
            description = response.choices[0].message.content
            usage = response.usage
            
            # Calculate cost
            cost = self._calculate_cost(usage.prompt_tokens, usage.completion_tokens)
            
            # Log token usage
            logger.info(f"GPT-4 Vision: {usage.total_tokens} tokens (${cost:.6f})")
            
            return {
                "description": description.strip(),
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
                "model": self.model,
                "cost": cost
            }
        
        except Exception as e:
            logger.error(f"GPT-4 Vision failed: {e}")
            return {
                "description": "",  # ✅ 返回空字串，不污染資料
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "model": self.model,
                "cost": 0.0
            }
    
    def _calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """
        Calculate cost based on token usage
        
        Pricing (per 1M tokens):
        - gpt-4o: $5.00 input, $15.00 output
        - gpt-4o-mini: $0.15 input, $0.60 output
        """
        pricing = {
            "gpt-4o": {"input": 5.00, "output": 15.00},
            "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        }
        
        # Get pricing for current model (default to gpt-4o if unknown)
        model_pricing = pricing.get(self.model, pricing["gpt-4o"])
        
        input_cost = (prompt_tokens / 1_000_000) * model_pricing["input"]
        output_cost = (completion_tokens / 1_000_000) * model_pricing["output"]
        
        return input_cost + output_cost
    
    def is_available(self) -> bool:
        """Check if GPT-4 Vision is available"""
        try:
            # Simple check: see if we can create the client
            return self.client is not None
        except:
            return False
