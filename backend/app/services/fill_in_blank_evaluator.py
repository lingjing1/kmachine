"""
填空題智慧評分模組

提供字串正規化與模糊比對功能，替代原本的精確字串比對。
支援：
- 去除括號內容：機器學習(Machine Learning) → 機器學習
- 全形→半形轉換：ＡＩ → AI
- 移除標點符號
- difflib.SequenceMatcher 模糊比對
- 多正確答案（以 | 分隔）
"""

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Tuple


# 相似度門檻
THRESHOLD_CORRECT = 0.8        # ≥ 0.8 → correct
THRESHOLD_PARTIAL = 0.5        # 0.5 ~ 0.8 → partially_correct


def normalize_text(text: str) -> str:
    """
    正規化文字：
    1. 去除括號及其內容（支援 ()（）[]）
    2. 全形英數→半形
    3. 移除常見標點
    4. 壓縮連續空白
    5. strip + lower
    """
    if not text:
        return ""

    s = text

    # 1. 去除各種括號及其內容
    s = re.sub(r'[(\（\[](.*?)[)\）\]]', '', s)

    # 2. 全形英數→半形 (NFKC 正規化)
    s = unicodedata.normalize('NFKC', s)

    # 3. 移除常見中英文標點
    s = re.sub(r'[。、，；：！？\.\,\;\:\!\?\-\_\'\"\`\~\@\#\$\%\^\&\*\+\=\<\>\{\}\/\\]', '', s)

    # 4. 壓縮連續空白為單一空格
    s = re.sub(r'\s+', ' ', s)

    # 5. strip + lower
    return s.strip().lower()


def _compute_similarity(a: str, b: str) -> float:
    """計算兩個字串的相似度 (0.0 ~ 1.0)"""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def evaluate_fill_in_blank(
    student_answer: str,
    correct_answer: str,
) -> Tuple[str, str]:
    """
    填空題智慧評分

    Args:
        student_answer: 學生作答內容
        correct_answer: 正確答案（多答案以 | 分隔）

    Returns:
        (correctness, feedback)
        correctness: 'correct' | 'partially_correct' | 'incorrect'
        feedback: 評分回饋文字
    """
    if not student_answer or not student_answer.strip():
        return 'incorrect', f'未作答。正確答案應為：{correct_answer}'

    if not correct_answer or not correct_answer.strip():
        return 'unknown', '缺少正確答案，無法評分'

    # 拆分多正確答案
    answer_variants = [a.strip() for a in correct_answer.split('|') if a.strip()]

    student_normalized = normalize_text(student_answer)

    best_similarity = 0.0
    matched_answer = answer_variants[0] if answer_variants else correct_answer

    for variant in answer_variants:
        variant_normalized = normalize_text(variant)

        # 精確比對（正規化後）
        if student_normalized == variant_normalized:
            return 'correct', '填寫正確！'

        # 計算相似度
        sim = _compute_similarity(student_normalized, variant_normalized)
        if sim > best_similarity:
            best_similarity = sim
            matched_answer = variant

    # 根據最高相似度決定結果
    if best_similarity >= THRESHOLD_CORRECT:
        return 'correct', '填寫正確！'
    elif best_similarity >= THRESHOLD_PARTIAL:
        return (
            'partially_correct',
            f'填寫部分正確，但不夠精確。正確答案應為：{matched_answer}'
        )
    else:
        return 'incorrect', f'填寫錯誤。正確答案應為：{correct_answer}'
