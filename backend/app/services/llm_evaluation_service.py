
from typing import Tuple, Dict, Optional
import json
import os
import difflib
from openai import OpenAI
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

from backend.app.config.settings import settings

# 初始化 OpenAI client
openai_client = None
if settings.openai_api_key:
    openai_client = OpenAI(api_key=settings.openai_api_key)

async def evaluate_answer_with_llm(
    question: str,
    reference_answer: str,
    student_answer: str,
    max_retries: int = 3
) -> Tuple[str, str]:
    """
    使用 GPT-4o mini 評估學生答案
    
    Args:
        question: 題目
        reference_answer: 參考答案
        student_answer: 學生回答
        max_retries: 最大重試次數
    
    Returns:
        (correctness, feedback)
        correctness: 'correct', 'partially_correct', 'incorrect'
        feedback: 評估回饋說明
    """
    
    # Fallback: 如果沒有 OpenAI API key，使用簡單比對
    if not openai_client:
        if not student_answer or student_answer.strip() == "":
            return "incorrect", "未作答"
        
        similarity = calculate_similarity(reference_answer, student_answer)
        
        if similarity > 0.8:
            return "correct", "答案正確！（使用 fallback 評分）"
        elif similarity > 0.5:
            return "partially_correct", "答案部分正確，但還可以更完整。（使用 fallback 評分）"
        else:
            return "incorrect", "答案不正確，請參考參考答案重新思考。（使用 fallback 評分）"
    
    # System prompt（更新：需生成回饋與詳細解說）
    system_prompt = """你是一個機器學習課程的評分助教。你的任務是評估學生的簡答題回答品質。
請以「概念理解是否正確」為主要評分依據，不需要求學生用詞和參考答案完全一致。

評分標準（3個等級）：

1. **Correct（正確）**: 
   - 學生答案掌握了題目的核心概念，語意正確即可
   - 用自己的話說明也算正確，不需與參考答案逐字相符
   - 即使表達不夠完整，只要核心觀念正確且沒有明顯錯誤，應判為 Correct
   
2. **Partially Correct（部分正確）**: 
   - 答案有觸及部分正確概念，但同時包含錯誤陳述，或嚴重遺漏關鍵概念
   - 方向正確但理解明顯不足或有重要誤解
   
3. **Incorrect（錯誤）**: 
   - 學生答案與正確概念明確矛盾，或完全離題、未作答
   - 僅因「說得不夠詳細」或「用詞不同」不應判為 Incorrect

請以 JSON 格式回應，包含以下欄位：
{
  "label": "Correct" | "Partially Correct" | "Incorrect",
  "feedback_for_student": "給學生的直接回饋建議（針對其答案的具體優缺點，語氣鼓勵但明確）",
  "explanation": "詳細的概念解說與正確答案解析（作為題目引導使用，幫助學生理解核心觀念）"
}"""
    
    user_prompt = f"""題目: {question}

學生回答: {student_answer}

參考答案: {reference_answer}

請評估學生回答的正確性，並提供回饋與解析。"""
    
    # 重試邏輯
    for attempt in range(max_retries):
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=500
            )
            
            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response content")
                
            result = json.loads(content)
            
            # 驗證格式
            if 'label' not in result:
                raise ValueError("Response missing 'label' field")
            
            label = result['label']
            feedback = result.get('feedback_for_student', '')
            explanation = result.get('explanation', '')
            
            if label not in ['Correct', 'Partially Correct', 'Incorrect']:
                raise ValueError(f"Invalid label: {label}")
            
            # 轉換為資料庫格式
            if label == 'Correct':
                correctness = 'correct'
                if not feedback: feedback = "答案正確！涵蓋了參考答案的所有主要概念。"
            elif label == 'Partially Correct':
                correctness = 'partially_correct'
                if not feedback: feedback = "答案部分正確，但有遺漏或不夠完整。"
            else:  # Incorrect
                correctness = 'incorrect'
                if not feedback: feedback = "答案不正確，請參考參考答案重新思考。"
            
            return correctness, feedback, explanation
            
        except json.JSONDecodeError as e:
            if attempt < max_retries - 1:
                print(f"  ⚠️  JSON 解析失敗，重試 {attempt + 1}/{max_retries}...")
                continue
            else:
                print(f"  ❌ JSON 解析失敗: {e}")
                return "incorrect", "評分系統錯誤，請稍後再試。", ""
                
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  ⚠️  API 錯誤，重試 {attempt + 1}/{max_retries}: {e}")
                continue
            else:
                print(f"  ❌ API 調用失敗: {e}")
                return "incorrect", "評分系統錯誤，請稍後再試。", ""
    
    return "incorrect", "評分系統錯誤，請稍後再試。", ""


async def generate_question_explanation(
    question: str,
    correct_answer: str,
    student_answer: str,
    question_type: str = 'multiple_choice',
    options: Optional[Dict[str, str]] = None,
    context: Optional[str] = None
) -> str:
    """
    為各類題型生成詳細解析（解析補充）
    """
    if not openai_client:
        return ""

    type_name_map = {
        'multiple_choice': '選擇題',
        'short_answer': '簡答題',
        'fill_in_blank': '填空題',
        'true_false': '是非題'
    }
    type_name = type_name_map.get(question_type, '題目')

    system_prompt = f"""你是一個機器學習課程的職業助教。你的任務是為這題{type_name}生成詳細的解析（Explanation）。
你的解析應對學生有教育意義，包含：
1. 為何正確答案是合理的。
2. 針對學生回答的情況指出其迷思或值得鼓勵的地方。
3. 若有提供上下文資料（教材內容），請結合該脈絡進行解釋。

請直接回傳解析內容，不需 JSON 格式，不需 "解析：" 等標題前綴。使用繁體中文。"""

    user_prompt = f"""題型: {type_name}
題目: {question}
正確答案: {correct_answer}
學生回答: {student_answer}
"""
    if options:
        user_prompt += f"選項: {json.dumps(options, ensure_ascii=False)}\n"
    if context:
        user_prompt += f"相關教材脈絡: {context}\n"

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=400
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        print(f"Error generating question explanation: {e}")
        return ""


def calculate_similarity(text1: str, text2: str) -> float:
    """
    簡單的文本相似度計算（示範用）
    使用 SequenceMatcher 計算字串相似度
    """
    if not text1 or not text2:
        return 0.0
        
    return difflib.SequenceMatcher(None, text1.lower(), text2.lower()).ratio()
