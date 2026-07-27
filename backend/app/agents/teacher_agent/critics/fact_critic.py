import logging
from typing import Dict, List, Any, Optional
from ragas.metrics import Faithfulness
from langchain_openai import ChatOpenAI
from langchain_openai import ChatOpenAI
import os
from backend.app.core.prompt_manager import prompt_manager
from backend.app.config.settings import settings

logger = logging.getLogger(__name__)

class CustomFaithfulness(Faithfulness):
    """
    Custom Faithfulness metric that generates specific Traditional Chinese feedback.
    Checks if the answer is supported by the retrieved contexts.
    """
    
    async def _ascore(self, row: Dict, callbacks: Any = None) -> float:
        """
        Manually implement Faithfulness evaluation to bypass Ragas JSON parsing issues.
        
        Logic:
        1. Extract statements from the response.
        2. Verify each statement against retrieved contexts.
        3. Calculate score = supported_statements / total_statements.
        """
        from langchain_core.messages import HumanMessage
        import json
        
        user_input = row.get('user_input', '')
        response = row.get('response', '')
        contexts = row.get('retrieved_contexts', [])
        
        if not contexts:
            logger.warning("No contexts retrieved for faithfulness check. Returning 0.0")
            return 0.0
            
        if not response:
            return 1.0 # No response means no hallucinations? Or 0? Let's say 1.0 for neutral.
            
        # Limit context size to avoid token overflow
        context_text = "\n\n".join(f"[Context {i+1}]: {ctx}" for i, ctx in enumerate(contexts[:5]))
        
        prompt = prompt_manager.get_prompt(
            "fact.check_faithfulness",
            context_text=context_text,
            user_input=user_input,
            response=response
        )
        try:
            # Use the same LLM configured for this critic
            if not self.llm:
                 from backend.app.agents.teacher_agent.critics.fact_critic import get_fact_critic_llm
                 self.llm = get_fact_critic_llm()

            response_msg = await self.llm.ainvoke([HumanMessage(content=prompt)])
            output = response_msg.content.strip()
            
            # Extract token usage
            token_usage = response_msg.response_metadata.get("token_usage", {})
            self._last_usage = {
                "prompt_tokens": token_usage.get("prompt_tokens", 0),
                "completion_tokens": token_usage.get("completion_tokens", 0),
                "model_name": getattr(self.llm, "model_name", "unknown")
            }
            
            # Robust JSON parsing
            if "```json" in output:
                output = output.split("```json")[1].split("```")[0].strip()
            elif "```" in output:
                output = output.split("```")[1].split("```")[0].strip()
                
            result = json.loads(output)
            
            # Store detail for feedback generation if needed
            self._last_result = result
            
            # Validate score range
            score = float(result.get("faithfulness_score", 0.0))
            return max(0.0, min(1.0, score))
            
        except Exception as e:
            logger.error(f"Custom Faithfulness evaluation failed: {e}")
            # Fallback to word overlap heuristic
            context_words = set(context_text.lower().split())
            response_words = set(response.lower().split())
            if not response_words: return 0.0
            overlap = len(context_words & response_words)
            # Normalize somewhat arbitrarily
            heuristic_score = min(1.0, overlap / (len(response_words) * 0.5 + 1))
            logger.warning(f"Using heuristic fallback score: {heuristic_score:.2f}")
            return heuristic_score
    
    async def _generate_feedback_with_llm(self, score: float, row: Dict, threshold: float = 0.625) -> Dict[str, Any]:
        """
        使用 LLM 生成分析與改進建議（參考 QualityCritic 的設計）
        
        Args:
            score: Ragas Faithfulness 的原始分數 (0-1)
            row: 評估資料
            threshold: 及格閾值（對應標準化分數 4）
        
        Returns:
            {"analysis": str, "suggestions": List[str]}
        """
        from langchain_core.messages import HumanMessage
        import json
        
        # 準備評估內容
        user_input = row.get('user_input', '')
        response = row.get('response', '')
        contexts = row.get('retrieved_contexts', [])
        
        # 標準化分數
        normalized_score = normalize_ragas_score(score)
        raw_linear_score = 1.0 + (score * 4.0)
        
        # Debug logging
        logger.info(f"🔍 Faithfulness LLM Feedback - Data Check:")
        logger.info(f"  - Ragas score: {score:.3f}")
        logger.info(f"  - Contexts count: {len(contexts)}")

        
        # 構建 prompt（參考 quality_critic 的 Analysis-Rate-Suggest 策略）
        prompt = prompt_manager.get_prompt(
            "fact.generate_feedback",
            score=score,
            normalized_score=normalized_score,
            threshold=threshold,
            user_input=user_input,
            response_preview=f"{response[:500]}{'...' if len(response) > 500 else ''}",
            contexts_preview=f"{chr(10).join(f'[Context {i+1}] {ctx[:300]}' for i, ctx in enumerate(contexts[:3])) if contexts else '⚠️ 無參考資料（這是異常情況，Ragas 評分可能不準確）'}"
        )
        
        try:
            llm = get_fact_critic_llm()
            messages = [HumanMessage(content=prompt)]
            response = await llm.ainvoke(messages)
            output = response.content.strip()
            
            # Parse JSON from response
            if "```json" in output:
                output = output.split("```json")[1].split("```")[0].strip()
            elif "```" in output:
                parts = output.split("```")
                if len(parts) >= 3:
                    output = parts[1].strip()
            
            parsed = json.loads(output)
            
            # Extract token usage
            token_usage = response.response_metadata.get("token_usage", {})
            
            return {
                "analysis": parsed.get("analysis", ""),
                "suggestions": parsed.get("suggestions", []),
                "prompt_tokens": token_usage.get("prompt_tokens", 0),
                "completion_tokens": token_usage.get("completion_tokens", 0),
                "model_name": getattr(llm, "model_name", "unknown")
            }
            
        except Exception as e:
            logger.error(f"LLM feedback generation failed: {e}")
            # Fallback to simple feedback
            if score < 0.5:
                return {
                    "analysis": f"Ragas Faithfulness 分數: {score:.2f}。答案中有多處陳述未得到上下文的支持。",
                    "suggestions": ["請逐句檢查答案，確保每個陳述都有明確的證據來源。"]
                }
            elif score < threshold:
                return {
                    "analysis": f"Ragas Faithfulness 分數: {score:.2f}。答案中部分陳述缺乏上下文支持。",
                    "suggestions": ["強化答案與原文的對應關係，移除無法驗證的推論。"]
                }
            else:
                return {
                    "analysis": f"Ragas Faithfulness 分數: {score:.2f}。答案大致正確。",
                    "suggestions": []
                }
    
    async def score_with_feedback(self, row: Dict, callbacks: Any = None) -> Dict[str, Any]:
        """
        Computes score and returns detailed LLM-generated feedback in Traditional Chinese.
        
        Args:
            row: Dict with keys:
                - 'user_input': The question
                - 'response': The answer to evaluate
                - 'retrieved_contexts': List of context strings
        
        Returns:
            Dict with:
                - 'score': float (0-1, 原始 Ragas 分數)
                - 'normalized_score': int (1-5, 標準化分數)
                - 'raw_linear_score': float (1-5, 線性映射未四捨五入)
                - 'analysis': str (LLM 生成的分析)
                - 'suggestions': List[str] (LLM 生成的建議)
        """
        score = None
        ragas_error = None
        
        # Try to get Ragas score
        try:
            score = await self._ascore(row, callbacks)
        except Exception as e:
            ragas_error = str(e)
            logger.warning(f"Ragas Faithfulness scoring failed (will use fallback): {ragas_error}")
            # Use a fallback heuristic score based on context overlap
            contexts = row.get('retrieved_contexts', [])
            response = row.get('response', '')
            if contexts and response:
                # Simple heuristic: check how many context keywords appear in response
                context_words = set(' '.join(contexts).lower().split())
                response_words = set(response.lower().split())
                overlap = len(context_words & response_words)
                total = len(context_words) if context_words else 1
                score = min(1.0, overlap / max(total * 0.3, 1))  # Normalize
            else:
                score = 0.5  # Neutral fallback
        
        try:
            # Generate LLM feedback (this uses our own code, not Ragas)
            llm_feedback = await self._generate_feedback_with_llm(score, row)
            
            # Calculate normalized score
            normalized_score = normalize_ragas_score(score)
            raw_linear_score = 1.0 + (score * 4.0)
            
            # Collect total tokens from _ascore and _generate_feedback
            total_prompt_tokens = llm_feedback.get("prompt_tokens", 0) + getattr(self, "_last_usage", {}).get("prompt_tokens", 0)
            total_completion_tokens = llm_feedback.get("completion_tokens", 0) + getattr(self, "_last_usage", {}).get("completion_tokens", 0)
            model_name = llm_feedback.get("model_name") or getattr(self, "_last_usage", {}).get("model_name", "unknown")

            result = {
                "score": score,
                "normalized_score": normalized_score,
                "raw_linear_score": raw_linear_score,
                "analysis": llm_feedback["analysis"],
                "suggestions": llm_feedback["suggestions"],
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_completion_tokens,
                "model_name": model_name
            }
            
            if ragas_error:
                result["warning"] = f"Ragas scoring failed, used heuristic fallback. Error: {ragas_error[:100]}"
            
            return result
            
        except Exception as e:
            logger.error(f"Error in CustomFaithfulness evaluation: {e}")
            import traceback
            traceback.print_exc()
            return {
                "score": score if score is not None else 0.0,
                "normalized_score": normalize_ragas_score(score) if score else 1,
                "raw_linear_score": 1.0 + ((score or 0) * 4.0),
                "analysis": f"評估過程發生錯誤：{str(e)}",
                "suggestions": [],
                "error": str(e)
            }


class TaskSatisfaction:
    """
    評估生成結果是否滿足使用者的基本任務要求（格式、數量等）。
    使用加權檢查項目計算 1-5 分。
    
    中文名稱：任務符合度
    """
    
    # 檢查項目定義（exam_generation）
    EXAM_CHECKS = [
        {"name": "question_count", "weight": 2, "description": "題目數量是否符合要求"},
        {"name": "question_type", "weight": 2, "description": "題型是否符合（選擇題/是非題/問答題）"},
        {"name": "has_options", "weight": 1, "description": "選擇題是否有 ABCD 選項"},
        {"name": "has_correct_answer", "weight": 2, "description": "是否有正確答案"},
        {"name": "has_source", "weight": 1, "description": "是否有來源引用"},
    ]
    
    def __init__(self):
        self.llm = None
    
    def detect_task_type(self, user_query: str) -> str:
        """
        根據使用者 query 自動偵測任務類型。
        
        Returns:
            "exam_generation" | "summary" | "generic"
        """
        query_lower = user_query.lower()
        
        # Exam generation keywords
        exam_keywords = [
            "題", "出題", "選擇題", "是非題", "問答題", "測驗", "考試",
            "quiz", "question", "exam", "test", "練習題", "習題"
        ]
        
        # Summary keywords
        summary_keywords = [
            "總結", "摘要", "整理", "歸納", "概述", "重點",
            "summarize", "summary", "overview", "outline"
        ]
        
        # Check for exam keywords
        for kw in exam_keywords:
            if kw in query_lower:
                return "exam_generation"
        
        # Check for summary keywords
        for kw in summary_keywords:
            if kw in query_lower:
                return "summary"
        
        # Default to generic
        return "generic"
    
    async def evaluate(
        self,
        user_query: str,
        generated_content: Any,
        task_type: str = "auto"
    ) -> Dict[str, Any]:
        """
        評估生成結果是否滿足任務要求。
        
        Args:
            user_query: 使用者原始請求
            generated_content: 生成的內容（結構化或字串）
            task_type: 任務類型 ("auto" | "exam_generation" | "summary" | "generic")
        
        Returns:
            {
                "score": float (0-1),
                "normalized_score": int (1-5),
                "task_type": str,  # 偵測到的任務類型
                "checks": List[Dict],
                "weighted_score": int,
                "total_weight": int,
                "analysis": str,
                "suggestions": List[str]
            }
        """
        # Auto-detect task type if not specified
        if task_type == "auto":
            task_type = self.detect_task_type(user_query)

        # Run LLM-based evaluation for instruction following
        llm_result = await self._evaluate_with_llm(user_query, generated_content, task_type)
        
        if task_type == "exam_generation":
            rule_result = await self._evaluate_exam(user_query, generated_content)
            # Combine: Rule-based checks are good for counts, LLM is good for instructions
            combined_checks = rule_result["checks"] + llm_result.get("checks", [])
            
            # Weighted average logic (Rule-based has 60% weight, LLM has 40% for instructions)
            r_ratio = rule_result["score"]
            l_ratio = (llm_result.get("rating", 1) - 1) / 4.0
            
            final_ratio = (r_ratio * 0.6) + (l_ratio * 0.4)
            final_normalized = int(round(1 + (final_ratio * 4)))
            
            result = {
                "score": final_ratio,
                "normalized_score": final_normalized,
                "checks": combined_checks,
                "analysis": f"【格式檢查】：{rule_result['analysis']}\n【指令遵循】：{llm_result.get('analysis', '')}",
                "suggestions": list(set(rule_result["suggestions"] + llm_result.get("suggestions", [])))
            }
        else:
            # For summary and generic, trust LLM evaluation more
            result = {
                "score": (llm_result.get("rating", 1) - 1) / 4.0,
                "normalized_score": llm_result.get("rating", 1),
                "checks": llm_result.get("checks", []),
                "analysis": llm_result.get("analysis", ""),
                "suggestions": llm_result.get("suggestions", [])
            }
        
        # Add detected task_type to result
        result["task_type"] = task_type
        return result

    async def _evaluate_with_llm(self, user_query: str, generated_content: Any, task_type: str) -> Dict[str, Any]:
        """Use LLM to evaluate instruction following based on prompts from critics.yaml"""
        if not self.llm:
            from backend.app.agents.teacher_agent.critics.fact_critic import get_fact_critic_llm
            self.llm = get_fact_critic_llm()
            
        content_preview = str(generated_content)[:5000] # Limit size
        prompt = prompt_manager.get_prompt(
            "fact.task_satisfaction",
            task_type=task_type,
            user_query=user_query,
            generated_content=content_preview
        )
        
        try:
            response = await self.llm.ainvoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            
            # Extract JSON
            import re
            json_match = re.search(r'(\{.*\})', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))
            return {"rating": 3, "analysis": "無法解析評估報告。", "suggestions": []}
        except Exception as e:
            logger.error(f"Error in LLM task satisfaction evaluation: {e}")
            return {"rating": 3, "analysis": f"評估過程出錯: {str(e)}", "suggestions": []}
    
    async def _evaluate_exam(self, user_query: str, generated_content: Any) -> Dict[str, Any]:
        """評估題目生成結果"""
        checks = []
        
        # 解析生成內容
        questions = self._extract_questions(generated_content)
        
        # 解析使用者要求
        requirements = await self._parse_requirements(user_query)
        
        # 1. 檢查題目數量
        expected_count = requirements.get("count", 0)
        actual_count = len(questions)
        count_passed = (expected_count == 0) or (actual_count == expected_count)
        checks.append({
            "name": "question_count",
            "weight": 2,
            "passed": count_passed,
            "expected": expected_count if expected_count > 0 else "未指定",
            "actual": actual_count
        })
        
        # 2. 檢查題型
        expected_type = requirements.get("type", "")
        actual_types = self._detect_question_types(questions)
        type_passed = (not expected_type) or (expected_type in actual_types)
        checks.append({
            "name": "question_type",
            "weight": 2,
            "passed": type_passed,
            "expected": expected_type if expected_type else "未指定",
            "actual": ", ".join(actual_types) if actual_types else "未知"
        })
        
        # 3. 檢查選項（僅選擇題）
        has_options = all(
            self._has_options(q) for q in questions 
            if self._is_multiple_choice(q)
        )
        # 如果沒有選擇題，視為通過
        options_applicable = any(self._is_multiple_choice(q) for q in questions)
        checks.append({
            "name": "has_options",
            "weight": 1,
            "passed": has_options if options_applicable else True,
            "note": "N/A (非選擇題)" if not options_applicable else None
        })
        
        # 4. 檢查正確答案
        has_answers = all(self._has_answer(q) for q in questions)
        checks.append({
            "name": "has_correct_answer",
            "weight": 2,
            "passed": has_answers
        })
        
        # 5. 檢查來源引用
        has_sources = all(self._has_source(q) for q in questions)
        checks.append({
            "name": "has_source",
            "weight": 1,
            "passed": has_sources
        })
        
        # 計算加權分數
        weighted_score = sum(c["weight"] for c in checks if c["passed"])
        total_weight = sum(c["weight"] for c in checks)
        
        # 轉換為 1-5 分
        ratio = weighted_score / total_weight if total_weight > 0 else 0
        raw_score = 1 + (ratio * 4)
        normalized_score = int(round(raw_score))
        
        # 生成分析和建議
        analysis, suggestions = self._generate_feedback(checks, ratio)
        
        return {
            "score": ratio,
            "normalized_score": normalized_score,
            "checks": checks,
            "weighted_score": weighted_score,
            "total_weight": total_weight,
            "analysis": analysis,
            "suggestions": suggestions,
            "llm_usage": self.get_llm_usage()  # Include LLM cost for database logging
        }
    
    async def _evaluate_summary(self, user_query: str, generated_content: Any) -> Dict[str, Any]:
        """評估摘要生成結果（簡化版，可後續擴充）"""
        checks = []
        
        content_str = str(generated_content) if generated_content else ""
        
        # 1. 檢查是否有內容
        has_content = len(content_str.strip()) > 50
        checks.append({
            "name": "has_content",
            "weight": 3,
            "passed": has_content
        })
        
        # 2. 檢查長度合理性
        reasonable_length = 50 < len(content_str) < 5000
        checks.append({
            "name": "reasonable_length",
            "weight": 2,
            "passed": reasonable_length
        })
        
        # 計算分數
        weighted_score = sum(c["weight"] for c in checks if c["passed"])
        total_weight = sum(c["weight"] for c in checks)
        ratio = weighted_score / total_weight if total_weight > 0 else 0
        raw_score = 1 + (ratio * 4)
        normalized_score = int(round(raw_score))
        
        analysis = "摘要生成結果評估完成。" if ratio >= 0.8 else "摘要生成結果有待改進。"
        suggestions = [] if ratio >= 0.8 else ["請確保摘要內容完整且長度適中。"]
        
        return {
            "score": ratio,
            "normalized_score": normalized_score,
            "checks": checks,
            "weighted_score": weighted_score,
            "total_weight": total_weight,
            "analysis": analysis,
            "suggestions": suggestions
        }
    
    async def _evaluate_generic(self, user_query: str, generated_content: Any) -> Dict[str, Any]:
        """通用評估（fallback）"""
        has_content = bool(generated_content)
        ratio = 1.0 if has_content else 0.0
        
        return {
            "score": ratio,
            "normalized_score": 5 if has_content else 1,
            "checks": [{"name": "has_content", "weight": 1, "passed": has_content}],
            "weighted_score": 1 if has_content else 0,
            "total_weight": 1,
            "analysis": "已生成內容。" if has_content else "未生成任何內容。",
            "suggestions": [] if has_content else ["請重新嘗試生成。"]
        }
    
    def _extract_questions(self, content: Any) -> List[Dict]:
        """從生成內容中提取題目列表"""
        if isinstance(content, list):
            # 可能是直接的題目列表
            questions = []
            for item in content:
                if isinstance(item, dict):
                    if "questions" in item:
                        # Copy block-level type to individual questions
                        block_type = item.get("type", "")
                        for q in item["questions"]:
                            if isinstance(q, dict) and not q.get("question_type"):
                                q["question_type"] = block_type
                        questions.extend(item["questions"])
                    elif "question" in item or "stem" in item or "statement_text" in item:
                        questions.append(item)
            return questions if questions else content
        elif isinstance(content, dict):
            if "questions" in content:
                # Copy type to individual questions
                block_type = content.get("type", "")
                for q in content["questions"]:
                    if isinstance(q, dict) and not q.get("question_type"):
                        q["question_type"] = block_type
                return content["questions"]
            elif "content" in content:
                return self._extract_questions(content["content"])
        elif isinstance(content, str):
            # 嘗試從字串中計算題目數量（簡化）
            import re
            matches = re.findall(r'(?:題目|問題|Question)\s*\d+', content, re.IGNORECASE)
            return [{"raw": m} for m in matches] if matches else []
        return []
    
    async def _parse_requirements(self, user_query: str) -> Dict[str, Any]:
        """
        解析使用者要求的題目數量和題型
        
        使用混合式方法：
        1. 先嘗試規則式匹配（快速、零成本）
        2. 如果題型未識別，用 LLM fallback（確保準確性）
        """
        import re
        
        requirements = {"count": 0, "type": "", "parse_method": "rules"}
        
        # Step 1: 規則式解析數量
        count_patterns = [
            r'(\d+)\s*題',
            r'(\d+)\s*道',
            r'出\s*(\d+)',
            r'生成\s*(\d+)',
        ]
        for pattern in count_patterns:
            match = re.search(pattern, user_query)
            if match:
                requirements["count"] = int(match.group(1))
                break
        
        # Step 2: 規則式解析題型 (按優先序)
        type_mapping = [
            (["選擇", "multiple choice", "mc"], "multiple_choice"),
            (["是非", "判斷", "true false", "對錯"], "true_false"),
            (["填空", "fill in", "blank"], "fill_in_blank"),
            (["簡答", "問答", "short answer"], "short_answer"),
        ]
        
        query_lower = user_query.lower()
        for keywords, q_type in type_mapping:
            if any(kw in query_lower for kw in keywords):
                requirements["type"] = q_type
                break
        
        # Step 3: 如果題型未識別，用 LLM fallback
        if not requirements["type"]:
            llm_result = await self._parse_requirements_by_llm(user_query)
            if llm_result:
                requirements["type"] = llm_result.get("type", "")
                requirements["count"] = llm_result.get("count", requirements["count"])
                requirements["parse_method"] = "llm"
        
        return requirements
    
    async def _parse_requirements_by_llm(self, user_query: str) -> Optional[Dict[str, Any]]:
        """
        使用 LLM 解析使用者要求（規則式失敗時的 fallback）
        """
        import json
        import logging
        
        if not self.llm:
            from backend.app.agents.teacher_agent.critics.fact_critic import get_fact_critic_llm
            self.llm = get_fact_critic_llm()
        
        prompt = prompt_manager.get_prompt("fact.parse_requirements", user_query=user_query)

        try:
            response = await self.llm.ainvoke(prompt)
            content = response.content.strip()
            
            # 嘗試解析 JSON
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            
            result = json.loads(content)
            
            # 記錄 LLM 成本
            token_usage = response.response_metadata.get("token_usage", {})
            prompt_tokens = token_usage.get("prompt_tokens", 0)
            completion_tokens = token_usage.get("completion_tokens", 0)
            
            # 累加到 TaskSatisfaction 的成本追蹤
            if not hasattr(self, '_llm_usage'):
                self._llm_usage = {"prompt_tokens": 0, "completion_tokens": 0}
            self._llm_usage["prompt_tokens"] += prompt_tokens
            self._llm_usage["completion_tokens"] += completion_tokens
            
            logging.info(f"📊 TaskSatisfaction LLM fallback used: {prompt_tokens}+{completion_tokens} tokens")
            
            result["prompt_tokens"] = prompt_tokens
            result["completion_tokens"] = completion_tokens
            result["model_name"] = getattr(self.llm, "model_name", "unknown")
            
            return result
            
        except Exception as e:
            import logging
            logging.warning(f"LLM parse requirements failed: {e}")
            return None
    
    def get_llm_usage(self) -> Dict[str, int]:
        """取得此次評估的 LLM 使用量"""
        return getattr(self, '_llm_usage', {"prompt_tokens": 0, "completion_tokens": 0})
    
    def _detect_question_types(self, questions: List[Dict]) -> List[str]:
        """檢測題目類型"""
        types = set()
        for q in questions:
            if isinstance(q, dict):
                q_type = q.get("type", q.get("question_type", ""))
                if q_type:
                    types.add(q_type)
                elif q.get("options") or q.get("choices"):
                    types.add("multiple_choice")
        return list(types)
    
    def _is_multiple_choice(self, question: Dict) -> bool:
        """判斷是否為選擇題"""
        if isinstance(question, dict):
            q_type = question.get("type", question.get("question_type", ""))
            return q_type == "multiple_choice" or bool(question.get("options") or question.get("choices"))
        return False
    
    def _has_options(self, question: Dict) -> bool:
        """檢查是否有選項"""
        if isinstance(question, dict):
            options = question.get("options") or question.get("choices") or []
            return len(options) >= 2
        return False
    
    def _has_answer(self, question: Dict) -> bool:
        """檢查是否有答案"""
        if isinstance(question, dict):
            return bool(
                question.get("correct_answer") or 
                question.get("answer") or 
                question.get("correct_option")
            )
        return False
    
    def _has_source(self, question: Dict) -> bool:
        """檢查是否有來源引用"""
        if isinstance(question, dict):
            return bool(
                question.get("source") or 
                question.get("source_page") or 
                question.get("evidence") or
                question.get("sources")
            )
        return False
    
    def _generate_feedback(self, checks: List[Dict], ratio: float) -> tuple:
        """生成分析和建議"""
        failed_checks = [c for c in checks if not c["passed"]]
        
        if ratio >= 0.875:
            analysis = "生成結果完全符合要求，所有檢查項目均通過。"
            suggestions = []
        elif ratio >= 0.625:
            analysis = f"生成結果大致符合要求，但有 {len(failed_checks)} 項未通過。"
            suggestions = [f"改進 {c['name']}" for c in failed_checks]
        else:
            analysis = f"生成結果不符合要求，有 {len(failed_checks)} 項重要檢查未通過。"
            suggestions = [f"必須改進 {c['name']}" for c in failed_checks]
        
        return analysis, suggestions


def normalize_ragas_score(ragas_score: float) -> int:
    """
    將 Ragas 的 0-1 分數標準化為 1-5 分（整數）
    
    使用線性映射 + 四捨五入方法：
    raw_score = 1 + (ragas_score × 4)
    normalized_score = round(raw_score)
    
    實際映射（四捨五入後）：
    [0.0, 0.125) → 1
    [0.125, 0.375) → 2
    [0.375, 0.625) → 3
    [0.625, 0.875) → 4
    [0.875, 1.0] → 5
    
    Args:
        ragas_score: Ragas 原始分數 (0.0-1.0)
    
    Returns:
        整數分數 1-5，與 G-Eval 對齊
        
    Examples:
        >>> normalize_ragas_score(0.1)   # → 1
        >>> normalize_ragas_score(0.3)   # → 2
        >>> normalize_ragas_score(0.5)   # → 3
        >>> normalize_ragas_score(0.7)   # → 4 (原本的閾值)
        >>> normalize_ragas_score(0.9)   # → 5
    """
    # Clamp to [0, 1]
    ragas_score = max(0.0, min(1.0, ragas_score))
    
    # Linear mapping
    raw_score = 1.0 + (ragas_score * 4.0)
    
    # Round to nearest integer
    return int(round(raw_score))


def get_fact_critic_llm() -> ChatOpenAI:
    """
    Get LLM for fact critic using Cook.ai project settings.
    """
    return ChatOpenAI(model=settings.agent.generator_model, temperature=0)

