"""
LIME 可解釋性服務

使用 LIME (Local Interpretable Model-agnostic Explanations) 解釋 RoBERTa 模型的預測結果。
支援 LLM 關鍵詞提取和視覺化報告生成。

此模組可被 Preview 和 Review 階段共用。
"""

import os
import re
import json
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from lime.lime_text import LimeTextExplainer
from dotenv import load_dotenv
from openai import OpenAI

from .bert_mastery_service import get_bert_mastery_service
from backend.app.config.settings import settings

# 載入環境變數
load_dotenv()


class LIMEExplainerService:
    """
    LIME 可解釋性服務（Singleton 模式）
    
    使用 LIME 解釋 RoBERTa 模型的 Mastery 預測結果。
    """
    
    _instance: Optional['LIMEExplainerService'] = None
    _initialized: bool = False
    
    def __new__(cls) -> 'LIMEExplainerService':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.class_names = ["待加強", "尚可", "精熟"]
        self.bert_service = get_bert_mastery_service()
        
        # 初始化 OpenAI client
        api_key = settings.openai_api_key
        if api_key:
            self.openai_client = OpenAI(api_key=api_key)
            self.openai_model = settings.agent.generator_model
            self.use_llm_keywords = True
            print(f"LIME: LLM 關鍵詞提取已啟用 (model: {self.openai_model})")
        else:
            self.openai_client = None
            self.use_llm_keywords = False
            print("⚠️  LIME: 未設定 OPENAI_API_KEY，關鍵詞提取已停用")
        
        self._initialized = True
    
    def _extract_keywords_with_llm(self, text: str) -> List[str]:
        """
        使用 LLM 從學生回答中提取有意義的關鍵詞
        
        Args:
            text: 學生回答文本
            
        Returns:
            提取的關鍵詞列表
        """
        if not self.use_llm_keywords or not text.strip():
            return []
        
        prompt = f"""請從以下學生簡答題回答中提取 2-5 個最重要的專業術語或核心概念詞彙。

重要指引：
1. **提取 2-5 個**，不要超過 5 個
2. **只提取**：專業術語、技術名詞、核心概念
3. **必須排除**：疑問詞（什麼、如何、為何）、語氣詞、連接詞、介詞、代詞
4. 關鍵詞應該是名詞或名詞短語，能反映學生理解的專業知識點

學生回答：
{text}

請以 JSON 陣列格式輸出，例如：["機器學習", "監督式學習", "神經網絡"]
只輸出 JSON，不要其他文字。"""

        try:
            response = self.openai_client.chat.completions.create(
                model=self.openai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300
            )
            
            content = response.choices[0].message.content.strip()
            
            # 嘗試解析 JSON
            if content.startswith('['):
                keywords = json.loads(content)
            else:
                match = re.search(r'\[.*?\]', content, re.DOTALL)
                if match:
                    keywords = json.loads(match.group())
                else:
                    return []
            
            print(f"✅ LIME: LLM 提取了 {len(keywords)} 個關鍵詞: {keywords}")
            return keywords
            
        except Exception as e:
            print(f"⚠️  LLM 關鍵詞提取失敗: {e}")
            return []
    
    def _extract_student_answers(self, short_answer_log: str) -> str:
        """從 Short_Answer_Log 提取學生答案與表現，作為 LIME 分析的輸入文本
        
        同時提取 ［學生答案］ 和 ［學生表現］，讓 LIME 能分析 correctness 對預測的影響。
        """
        parts = []
        
        # 提取答案+表現配對
        blocks = re.findall(
            r'(［學生答案］[:：]\s*.+?)(［學生表現］[:：]\s*.+?)(?=［|$)',
            short_answer_log,
            re.DOTALL
        )
        for ans_block, perf_block in blocks:
            ans_text = re.sub(r'^［學生答案］[:：]\s*', '', ans_block).strip()
            perf_text = re.sub(r'^［學生表現］[:：]\s*', '', perf_block).strip()
            parts.append(f"{ans_text} [{perf_text}]")
        
        # 如果配對提取失敗，退而求其次只提取答案
        if not parts:
            student_answers = re.findall(
                r'［學生答案］[:：]\s*(.+?)(?=［|$)',
                short_answer_log,
                re.DOTALL
            )
            parts = [ans.strip() for ans in student_answers]
        
        return " | ".join(parts) if parts else short_answer_log
    
    # def _extract_student_questions(self, dialog: str) -> str:
    #     """從 Dialog 提取學生提問"""
    #     student_questions = re.findall(
    #         r'\[學生\][:：]\s*(.+?)(?=\[AI Tutor\]|\[學生\]|$)', 
    #         dialog, 
    #         re.DOTALL
    #     )
    #     return " ".join([q.strip() for q in student_questions])
    
    def _predict_batch(self, texts: List[str], base_sample: Dict) -> np.ndarray:
        """
        批次預測（用於 LIME）
        
        Args:
            texts: 要預測的文本列表
            base_sample: 基礎樣本（用於填充其他欄位）
            
        Returns:
            預測機率陣列 (n_samples, n_classes)
        """
        import torch
        
        # 構建完整樣本並格式化
        formatted_texts = []
        for t in texts:
            sample = base_sample.copy()
            # 將擾動文本放入 Short_Answer_Log
            sample['Short_Answer_Log'] = f"［學生答案］：{t}"
            formatted_texts.append(self.bert_service._format_input(sample))
        
        # 確保模型已載入
        if not self.bert_service._load_model():
            # Fallback: 返回均勻分布
            return np.ones((len(texts), 3)) / 3
        
        # Tokenize
        encoding = self.bert_service.tokenizer(
            formatted_texts,
            add_special_tokens=True,
            max_length=self.bert_service.max_len,
            padding="max_length",
            truncation=True,
            return_tensors="pt"
        )
        
        input_ids = encoding['input_ids'].to(self.bert_service.device)
        attention_mask = encoding['attention_mask'].to(self.bert_service.device)
        
        # 批次推論
        batch_size = 16
        probs_list = []
        
        with torch.no_grad():
            for i in range(0, len(formatted_texts), batch_size):
                batch_ids = input_ids[i:i+batch_size]
                batch_mask = attention_mask[i:i+batch_size]
                
                outputs = self.bert_service.model(input_ids=batch_ids, attention_mask=batch_mask)
                logits = outputs.logits
                batch_probs = torch.softmax(logits, dim=1).cpu().numpy()
                probs_list.append(batch_probs)
        
        return np.concatenate(probs_list, axis=0)
    
    def explain(
        self,
        sample: Dict,
        focus_on: str = "student_answers",
        num_features: int = 10,
        num_samples: int = 500
    ) -> Tuple[Optional[object], List[str], Dict]:
        """
        生成 LIME 解釋
        
        Args:
            sample: 包含 chapter, section, Short_Answer_Log 的樣本
            focus_on: 分析焦點 ('student_answers' 或 'full_text')
            num_features: 要顯示的特徵數量
            num_samples: LIME 擾動樣本數
            
        Returns:
            (explanation, keywords, prediction_result)
        """
        # 1. 獲取預測結果
        prediction_result = self.bert_service.predict(sample)
        
        # 2. 提取焦點文本
        if focus_on == "student_answers":
            text_to_explain = self._extract_student_answers(sample.get('Short_Answer_Log', ''))
        else:  # full_text
            text_to_explain = self.bert_service._format_input(sample)
        
        if not text_to_explain.strip():
            return None, [], prediction_result
        
        # 3. LLM 關鍵詞提取
        keywords = []
        if self.use_llm_keywords and focus_on != "full_text":
            # 答案太短直接用原文，不呼叫 LLM（省時省錢，且短文提取無意義）
            if len(text_to_explain.strip()) < 8:
                print(f"⚠️  LIME: 學生回答過短（{len(text_to_explain.strip())} 字），跳過 LLM 提取")
            else:
                keywords = self._extract_keywords_with_llm(text_to_explain)
        
        # 4. 如果有關鍵詞，使用關鍵詞作為分析單位
        # 強制注入 correctness 標籤（incorrect / partially_correct / correct）
        # 讓 LIME 分析這些表現標籤對掌握度預測的影響
        correctness_in_text = re.findall(
            r'\[(incorrect|partially_correct|correct)\]',
            text_to_explain
        )
        for ct in set(correctness_in_text):
            if ct not in keywords:
                keywords.append(ct)
        
        if keywords:
            delimiter = "|||"
            text_to_explain = delimiter.join(keywords)
            split_fn = lambda x: x.split(delimiter)
        else:
            split_fn = list  # 按字符分割
        
        # 5. 定義分類器函數
        def classifier_fn(texts):
            return self._predict_batch(texts, sample)
        
        # 6. 建立 LIME 解釋器
        explainer = LimeTextExplainer(
            class_names=self.class_names,
            split_expression=split_fn
        )
        
        # 7. 生成解釋
        try:
            exp = explainer.explain_instance(
                text_to_explain,
                classifier_fn,
                num_features=num_features,
                num_samples=num_samples,
                top_labels=3
            )
            return exp, keywords, prediction_result
        except Exception as e:
            print(f"❌ LIME 解釋生成失敗: {e}")
            return None, keywords, prediction_result
    
    def _get_student_text_regions(self, text: str) -> List[Tuple[int, int]]:
        """
        識別包含學生回答的文本區域（支援多題）
        
        Args:
            text: 完整文本
            
        Returns:
            [(start, end), ...] 區域列表，按位置排序
        """
        regions = []
        
        # 找出 Short_Answer_Log 中的所有 ［學生答案］ 區域
        # 使用全形方括號，匹配 ［學生答案］（與訓練資料格式一致）
        # 這個正則會找到所有匹配，所以可以處理多題的情況
        for match in re.finditer(r'［學生答案］[:：]\s*(.+?)(?=［|$)', text, re.DOTALL):
            regions.append((match.start(1), match.end(1)))
        
        # 按起始位置排序
        regions.sort(key=lambda x: x[0])
        return regions


    def generate_html_report(
        self,
        exp,
        keywords: List[str],
        prediction_result: Dict,
        original_text: str = None,
        title: str = "LIME Mastery 解釋報告",
        feature_weights: Optional[Dict[str, float]] = None
    ) -> str:
        """
        生成 HTML 報告（使用穩健的高亮邏輯）
        支援傳入 exp 物件或直接傳入 feature_weights
        
        Returns:
            HTML 內容字串
        """
        if exp is None and feature_weights is None:
            return "<html><body><h1>無法生成解釋報告</h1></body></html>"
            
        # 準備資料
        probs = []
        pred_label = 0
        
        if exp:
            # 從 exp 物件獲取
            pred_label = exp.top_labels[0] if exp.top_labels else 0
            feature_weights = dict(exp.as_list(label=pred_label))
            probs = exp.predict_proba
        else:
            # 從參數獲取 (Remote LIME case)
            # prediction_result 包含 probabilities Dict
            # 我們需要將其轉為 list 順序 [待加強, 尚可, 精熟]
            if "prediction_id" in prediction_result:
                pred_label = prediction_result["prediction_id"]
            
            if "probabilities" in prediction_result and isinstance(prediction_result["probabilities"], dict):
                probs = [
                    prediction_result["probabilities"].get(c, 0.0) 
                    for c in self.class_names
                ]
            else:
                probs = [0.0, 0.0, 0.0] # Fallback
                if 0 <= pred_label < 3:
                    probs[pred_label] = 1.0
        
        # Debug: 顯示權重分佈
        positive_weights = {k: v for k, v in feature_weights.items() if v > 0}
        negative_weights = {k: v for k, v in feature_weights.items() if v < 0}
        print(f"📊 LIME 權重分佈: 正向={len(positive_weights)}, 負向={len(negative_weights)}")
        if positive_weights:
            print(f"   正向關鍵詞: {positive_weights}")
        if negative_weights:
            print(f"   負向關鍵詞: {negative_weights}")
        
        # 機率顯示
        prob_html = ""
        for i, (label, prob) in enumerate(zip(self.class_names, probs)):
            color = "#22c55e" if i == pred_label else "#6b7280"
            weight = "bold" if i == pred_label else "normal"
            prob_html += f'<div style="margin: 5px 0;"><span style="color: {color}; font-weight: {weight};">{label}: {prob:.2%}</span></div>'
        
        # 特徵重要性表格
        feature_rows = ""
        sorted_features = sorted(feature_weights.items(), key=lambda x: abs(x[1]), reverse=True)
        for feature, weight in sorted_features:
            color = "#22c55e" if weight > 0 else "#ef4444"
            bar_width = min(abs(weight) * 200, 150)
            feature_rows += f'''
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">{feature}</td>
                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb; text-align: right;">
                    <span style="color: {color};">{weight:+.4f}</span>
                </td>
                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb; width: 200px;">
                    <div style="width: {bar_width}px; height: 16px; background-color: {color}; 
                                float: {"left" if weight > 0 else "right"}; border-radius: 3px;"></div>
                </td>
            </tr>'''
        
        # 原始文本高亮（穩健邏輯）
        highlighted_text = ""
        if original_text and keywords:
            # 獲取學生文本區域
            student_regions = self._get_student_text_regions(original_text)
            
            def is_in_student_region(pos):
                return any(start <= pos < end for start, end in student_regions)
            
            # 1. 找出所有關鍵詞匹配（僅在學生區域）
            all_matches = []
            
            for keyword in keywords:
                if keyword not in feature_weights:
                    # print(f"DEBUG: Keyword '{keyword}' not in weights")
                    continue
                    
                weight = feature_weights[keyword]
                # 使用 re.escape 確保特殊字符被正確處理
                for match in re.finditer(re.escape(keyword), original_text, re.IGNORECASE):
                    if is_in_student_region(match.start()):
                        all_matches.append({
                            "start": match.start(),
                            "end": match.end(),
                            "keyword": match.group(),
                            "weight": weight,
                            "length": match.end() - match.start()
                        })
                    else:
                        # print(f"DEBUG: Match '{match.group()}' at {match.start()} (Ignored: not in student region)")
                        pass
            
            # 2. 解決重疊：優先保留較長的關鍵詞（按長度降序，然後按位置）
            all_matches.sort(key=lambda x: (x['length'], -x['start']), reverse=True)
            
            occupied = [False] * len(original_text)
            final_matches = []
            
            for match in all_matches:
                # 檢查是否重疊
                if not any(occupied[i] for i in range(match['start'], match['end'])):
                    # 標記佔用並保留
                    for i in range(match['start'], match['end']):
                        occupied[i] = True
                    final_matches.append(match)
            
            # 3. 重組文本
            final_matches.sort(key=lambda x: x['start'])
            
            last_idx = 0
            segments = []
            
            for match in final_matches:
                # 加入未高亮部分
                segments.append(original_text[last_idx:match['start']])
                
                # 加入高亮部分
                weight = match['weight']
                match_text = original_text[match['start']:match['end']]
                
                if weight > 0:
                    bg_color = f"rgba(34, 197, 94, {min(abs(weight) * 2, 0.8)})"
                else:
                    bg_color = f"rgba(239, 68, 68, {min(abs(weight) * 2, 0.8)})"
                
                span = f'<span style="background-color: {bg_color}; padding: 2px 4px; border-radius: 3px; border: 1px solid rgba(0,0,0,0.1);" title="Weight: {weight:.4f}">{match_text}</span>'
                segments.append(span)
                
                last_idx = match['end']
            
            segments.append(original_text[last_idx:])
            highlighted_text = "".join(segments)
        else:
            highlighted_text = original_text or ""
        
        # 生成完整 HTML
        html_content = f'''<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
               max-width: 1200px; margin: 0 auto; padding: 20px; background: #f9fafb; }}
        .card {{ background: white; border-radius: 12px; padding: 24px; margin-bottom: 20px; 
                box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        h1 {{ color: #1f2937; margin-bottom: 8px; }}
        h2 {{ color: #374151; border-bottom: 2px solid #e5e7eb; padding-bottom: 8px; }}
        .prediction {{ font-size: 24px; font-weight: bold; color: #059669; }}
        .original-text {{ background: #f3f4f6; padding: 16px; border-radius: 8px; 
                         line-height: 1.8; white-space: pre-wrap; font-size: 14px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ text-align: left; padding: 12px 8px; background: #f9fafb; border-bottom: 2px solid #e5e7eb; }}
        .legend {{ display: flex; gap: 20px; margin-top: 10px; }}
        .legend-item {{ display: flex; align-items: center; gap: 8px; }}
        .legend-box {{ width: 20px; height: 20px; border-radius: 4px; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>🔍 {title}</h1>
        <p style="color: #6b7280;">RoBERTa 模型可解釋性分析報告</p>
        <p style="color: #9ca3af; font-size: 12px;">生成時間: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
    </div>
    
    <div class="card">
        <h2>📊 預測結果</h2>
        <div class="prediction">{self.class_names[pred_label]}</div>
        <div style="margin-top: 16px;">
            <strong>各類別機率：</strong>
            {prob_html}
        </div>
        <div style="margin-top: 16px;">
            <strong>信心度：</strong> {prediction_result.get("confidence", 0):.2%}
        </div>
    </div>
    
    {"<div class='card'><h2>📝 原始文本（關鍵詞高亮）</h2><div class='legend'><div class='legend-item'><div class='legend-box' style='background: rgba(34, 197, 94, 0.5);'></div><span>正向影響（支持預測）</span></div><div class='legend-item'><div class='legend-box' style='background: rgba(239, 68, 68, 0.5);'></div><span>負向影響（反對預測）</span></div></div><div class='original-text' style='margin-top: 16px;'>" + highlighted_text + "</div></div>" if highlighted_text else ""}
    
    <div class="card">
        <h2>📈 特徵重要性</h2>
        <table>
            <thead>
                <tr>
                    <th>關鍵詞</th>
                    <th style="text-align: right;">權重</th>
                    <th>影響程度</th>
                </tr>
            </thead>
            <tbody>
                {feature_rows}
            </tbody>
        </table>
    </div>
    
    <div class="card" style="text-align: center; color: #9ca3af; font-size: 12px;">
        Generated by Cook.ai LIME Explainer
    </div>
</body>
</html>'''
        
        return html_content


# 全域服務實例
_lime_service: Optional[LIMEExplainerService] = None


def get_lime_explainer_service() -> LIMEExplainerService:
    """獲取 LIME 服務實例（Singleton）"""
    global _lime_service
    if _lime_service is None:
        _lime_service = LIMEExplainerService()
    return _lime_service



async def explain_mastery(
    chapter: str,
    section: str,
    short_answer_log: str,
    focus_on: str = "student_answers",
    num_features: int = 10,
    num_samples: int = 500
) -> Dict:
    """
    異步包裝函數：生成 LIME 解釋（使用本地 GPU）
    """
    service = get_lime_explainer_service()
    
    sample = {
        "chapter": chapter,
        "section": section,
        "Short_Answer_Log": short_answer_log
    }
    
    exp, keywords, prediction = service.explain(
        sample,
        focus_on=focus_on,
        num_features=num_features,
        num_samples=num_samples
    )
    
    html_report = service.generate_html_report(
        exp,
        keywords,
        prediction,
        original_text=short_answer_log,
        title=f"知識點掌握度分析 - {section}"
    )
    
    feature_weights = {}
    if exp and exp.top_labels:
        feature_weights = dict(exp.as_list(label=exp.top_labels[0]))
    
    # ── 計算 highlighted_text（與 get_lime_report_json 相同邏輯）──
    highlighted_text = None
    if short_answer_log and keywords:
        student_regions = service._get_student_text_regions(short_answer_log)
        
        def is_in_student_region(pos):
            return any(start <= pos < end for start, end in student_regions)
        
        all_matches = []
        for keyword in keywords:
            if keyword not in feature_weights:
                continue
            weight = feature_weights[keyword]
            for match in re.finditer(re.escape(keyword), short_answer_log, re.IGNORECASE):
                if is_in_student_region(match.start()):
                    all_matches.append({
                        "start": match.start(),
                        "end": match.end(),
                        "keyword": match.group(),
                        "weight": weight,
                        "length": match.end() - match.start()
                    })
        
        # 解決重疊
        all_matches.sort(key=lambda x: (x['length'], -x['start']), reverse=True)
        occupied = [False] * len(short_answer_log)
        final_highlights = []
        for match in all_matches:
            if not any(occupied[i] for i in range(match['start'], match['end'])):
                for i in range(match['start'], match['end']):
                    occupied[i] = True
                final_highlights.append({
                    "start": match['start'],
                    "end": match['end'],
                    "keyword": match['keyword'],
                    "weight": match['weight']
                })
        final_highlights.sort(key=lambda x: x['start'])
        
        highlighted_text = {
            "original": short_answer_log,
            "highlights": final_highlights
        }
    
    return {
        "prediction": prediction["prediction"],
        "prediction_details": prediction,
        "keywords": keywords,
        "html_report": html_report,
        "feature_weights": feature_weights,
        "highlighted_text": highlighted_text
    }



async def get_lime_report_json(
    chapter: str,
    section: str,
    short_answer_log: str,
    focus_on: str = "student_answers",
    num_features: int = 10,
    num_samples: int = 500
) -> Dict:
    """
    生成 LIME 報告的 JSON 格式（供前端渲染）
    
    Returns:
        Dict 包含:
            - keywords: 提取的所有關鍵詞
            - feature_weights: List[{keyword, weight}] 按權重絕對值排序
            - highlighted_text: {original, highlights: List[{start, end, keyword, weight}]}
    """
    service = get_lime_explainer_service()
    
    sample = {
        "chapter": chapter,
        "section": section,
        "Short_Answer_Log": short_answer_log
    }
    
    exp, keywords, prediction = service.explain(
        sample,
        focus_on=focus_on,
        num_features=num_features,
        num_samples=num_samples
    )
    
    # 1. 獲取特徵權重並排序
    feature_weights_dict = {}
    if exp and exp.top_labels:
        feature_weights_dict = dict(exp.as_list(label=exp.top_labels[0]))
    
    # 按權重絕對值排序
    sorted_features = sorted(
        feature_weights_dict.items(),
        key=lambda x: abs(x[1]),
        reverse=True
    )
    
    feature_weights = [
        {"keyword": kw, "weight": weight}
        for kw, weight in sorted_features
    ]
    
    # 2. 生成高亮文本資料
    highlighted_text = None
    if short_answer_log and keywords:
        # 獲取學生文本區域
        student_regions = service._get_student_text_regions(short_answer_log)
        
        def is_in_student_region(pos):
            return any(start <= pos < end for start, end in student_regions)
        
        # 找出所有關鍵詞匹配
        all_matches = []
        for keyword in keywords:
            if keyword not in feature_weights_dict:
                continue
            
            weight = feature_weights_dict[keyword]
            for match in re.finditer(re.escape(keyword), short_answer_log, re.IGNORECASE):
                if is_in_student_region(match.start()):
                    all_matches.append({
                        "start": match.start(),
                        "end": match.end(),
                        "keyword": match.group(),
                        "weight": weight,
                        "length": match.end() - match.start()
                    })
        
        # 解決重疊
        all_matches.sort(key=lambda x: (x['length'], -x['start']), reverse=True)
        occupied = [False] * len(short_answer_log)
        final_highlights = []
        
        for match in all_matches:
            if not any(occupied[i] for i in range(match['start'], match['end'])):
                for i in range(match['start'], match['end']):
                    occupied[i] = True
                final_highlights.append({
                    "start": match['start'],
                    "end": match['end'],
                    "keyword": match['keyword'],
                    "weight": match['weight']
                })
        
        # 按位置排序
        final_highlights.sort(key=lambda x: x['start'])
        
        highlighted_text = {
            "original": short_answer_log,
            "highlights": final_highlights
        }
    
    return {
        "keywords": keywords,
        "feature_weights": feature_weights,
        "highlighted_text": highlighted_text
    }

