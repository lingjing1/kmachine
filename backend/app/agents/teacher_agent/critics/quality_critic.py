import asyncio
import json
import logging
from typing import Dict, List, Any, Optional
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.language_models import BaseChatModel
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from backend.app.core.prompt_manager import prompt_manager

logger = logging.getLogger(__name__)


# RUBRICS are now loaded from backend/app/config/prompts/critic_rubrics.yaml via prompt_manager


class QualityCritic:
    """
    Evaluates educational content quality using Analyze-rate strategy (based on G-Eval research).
    
    Strategy: Rationale-Based LLM Evaluation Framework
    1. Analyze: LLM analyzes content against rubrics with detailed reasoning
    2. Rate: LLM assigns 1-5 score based on analysis
    3. Suggest: LLM generates improvement suggestions (always present in output)
    
    Key improvements over basic G-Eval:
    - Forces LLM to provide analysis BEFORE rating (rationale-first approach)
    - Requires suggestions field to always exist (enhances output consistency)
    - Strict JSON validation with RFC 8259 compliance
    - Markdown code block wrapping for robust parsing
    """
    def __init__(self, llm: BaseChatModel, threshold: float = 4.0):
        """
        Args:
            llm: Language model for evaluation
            threshold: Score threshold for improvement suggestions emphasis (default 4.0)
        """
        self.llm = llm
        self.threshold = threshold
    
    def _get_criterion_focus(self, criteria: List[str]) -> str:
        """
        Generate criterion-specific focus guidance to separate evaluation responsibilities.
        """
        criteria = [c for c in criteria if c in ["Understandable", "Grammatical", "Logical_Consistency", "Phrasing"]]
        focus_texts = []
        for c in criteria:
            focus_text = prompt_manager.get_prompt(f"quality.focus.{c}")
            if focus_text:
                focus_texts.append(focus_text)
                
        return "\n".join(focus_texts)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception)
    )
    async def evaluate(self, content: Dict[str, Any], criteria: List[str] = None, user_query: str = "") -> Dict[str, Any]:
        """
        Evaluates a single content item using Analyze-rate strategy (based on G-Eval).
        
        Args:
            content: Content to evaluate (dict format, will be serialized to JSON)
            criteria: List of criteria names to evaluate. If None, evaluates all rubrics.
            user_query: Optional teacher instructions to check compliance
        
        Returns:
            Dict with structure:
            {
                "evaluations": [
                    {
                        "criteria": str,
                        "analysis": str (Traditional Chinese),
                        "rating": int (1-5),
                        "suggestions": List[str] (always present, empty if no issues)
                    }
                ]
            }
        """
        if criteria is None:
            # Use rubrics from prompt manager
            rubrics = prompt_manager.get_prompt("critic_rubrics")
            criteria = list(rubrics.keys()) if rubrics else []
            
        # Prepare content string
        content_str = json.dumps(content, ensure_ascii=False, indent=2)
        
        # Load rubrics again (or verify)
        rubrics = prompt_manager.get_prompt("critic_rubrics") or {}

        # Construct rubric text with evaluation steps
        rubric_sections = []
        for key in criteria:
            # Handle key mapping mismatch if YAML keys differ slightly from input criteria strings (e.g. spaces vs underscores)
            # YAML keys: Core_Concept_Focus, Would_You_Use_It
            # Legacy code might use "Core Concept Focus"
            
            # Simple normalization for lookup
            lookup_key = key.replace(" ", "_")
            
            if lookup_key in rubrics:
                r = rubrics[lookup_key]
                section = f"### {r.get('description', lookup_key)}\n"
                section += "**評分標準：**\n"
                for score in ["1", "2", "3", "4", "5"]:
                    if str(score) in r:
                         section += f"- {score} 分：{r[str(score)]}\n"
                rubric_sections.append(section)
            elif key in rubrics:
                 r = rubrics[key]
                 section = f"### {r.get('description', key)}\n"
                 section += "**評分標準：**\n"
                 for score in ["1", "2", "3", "4", "5"]:
                     if str(score) in r:
                         section += f"- {score} 分：{r[str(score)]}\n"
                 rubric_sections.append(section)
        
        rubric_text = "\n".join(rubric_sections)
        
        # Criterion-specific focus guidance
        criterion_focus = self._get_criterion_focus(criteria)
        
        # Improved prompt following Analyze-rate strategy with enhanced robustness
        prompt = prompt_manager.get_prompt(
            "quality.evaluate_system",
            criterion_focus=criterion_focus,
            threshold=self.threshold,
            rubric_text=rubric_text,
            content_str=content_str,
            user_query=user_query if user_query else "無預設指令"
        )
        
        messages = [HumanMessage(content=prompt)]
        
        try:
            # Call LLM with temperature=0 for consistency
            response = await self.llm.ainvoke(messages)
            output = response.content.strip()
            
            # Extract token usage
            token_usage = response.response_metadata.get("token_usage", {})
            model_name = getattr(self.llm, "model_name", "unknown")
            
            # Parse JSON from response
            parsed = self._parse_json_response(output)
            
            # Validate structure
            if "evaluations" not in parsed:
                raise ValueError("Response missing 'evaluations' key")
            
            # Strict validation: ensure all evaluations have required fields
            for i, eval_item in enumerate(parsed["evaluations"]):
                if "criteria" not in eval_item:
                    raise ValueError(f"Evaluation {i} missing 'criteria' field")
                if "analysis" not in eval_item:
                    raise ValueError(f"Evaluation {i} missing 'analysis' field")
                if "rating" not in eval_item:
                    raise ValueError(f"Evaluation {i} missing 'rating' field")
                
                # CRITICAL: suggestions must always exist (even if empty)
                if "suggestions" not in eval_item:
                    logger.warning(f"Evaluation {i} missing 'suggestions', adding empty array")
                    eval_item["suggestions"] = []
                
                # Validate rating range
                rating = eval_item.get("rating", 0)
                if not isinstance(rating, int) or rating < 1 or rating > 5:
                    raise ValueError(f"Invalid rating {rating} in evaluation {i}, must be 1-5")
            
            # Include usage metadata
            parsed["prompt_tokens"] = token_usage.get("prompt_tokens", 0)
            parsed["completion_tokens"] = token_usage.get("completion_tokens", 0)
            parsed["model_name"] = model_name
            
            return parsed
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON output: {e}\nRaw output: {output[:500]}")
            return {
                "error": "JSON parsing failed",
                "raw_output": output,
                "evaluations": [],
                "prompt_tokens": 0,
                "completion_tokens": 0
            }
        except Exception as e:
            logger.error(f"Error in evaluation: {e}")
            return {
                "error": str(e),
                "evaluations": [],
                "prompt_tokens": 0,
                "completion_tokens": 0
            }

    def _parse_json_response(self, output: str) -> Dict[str, Any]:
        """
        Parse JSON from LLM response, handling code blocks.
        """
        # Remove markdown code blocks if present
        if "```json" in output:
            output = output.split("```json")[1].split("```")[0].strip()
        elif "```" in output:
            # Try to extract content between first pair of ```
            parts = output.split("```")
            if len(parts) >= 3:
                output = parts[1].strip()
        
        # Parse JSON
        return json.loads(output)

    async def batch_evaluate(self, content_list: List[Dict[str, Any]], criteria: List[str] = None, user_query: str = "") -> List[Dict[str, Any]]:
        """
        Evaluate multiple content items.
        
        Args:
            content_list: List of content items to evaluate
            criteria: Criteria to use for all evaluations
            user_query: Optional teacher instructions
        
        Returns:
            List of evaluation results, one per content item
        """
        results = []
        for content in content_list:
            result = await self.evaluate(content, criteria, user_query)
            results.append(result)
        return results

    async def evaluate_exam(
        self, 
        exam: Dict[str, Any], 
        rag_content: str = None,
        criteria: List[str] = None,
        mode: str = "quick",
        user_query: str = ""
    ) -> Dict[str, Any]:
        """
        Evaluate an entire exam with different evaluation modes.
        
        Args:
            exam: Exam content with structure:
                {
                    "type": "multiple_choice" or "exam",
                    "questions": [
                        {"question_number": 1, "question_text": "...", ...},
                        {"question_number": 2, ...},
                        ...
                    ]
                }
            rag_content: Optional RAG context (retrieved educational material)
            criteria: List of criteria names to evaluate. If None, evaluates all rubrics.
            mode: Evaluation mode:
                - "quick" (default): Only overall evaluation, cost-effective
                - "comprehensive": Overall + per-question + statistics
        
        Returns:
            Dict with structure:
            {
                "mode": str,                # Evaluation mode used
                "overall": {...},           # Overall exam assessment
                "per_question": [...],      # Individual assessments (comprehensive only)
                "statistics": {...}         # Summary statistics (comprehensive only)
            }
        
        Example:
            # Quick mode (default)
            result = await critic.evaluate_exam(exam, rag_content="...", mode="quick")
            
            # Comprehensive mode
            result = await critic.evaluate_exam(exam, rag_content="...", mode="comprehensive")
        """
        # Add rag_content to exam if provided
        if rag_content:
            exam["rag_content"] = rag_content
        
        all_questions = exam.get("questions", [])
        results = {"mode": mode}
        
        # 1. Overall exam evaluation (always performed)
        logger.info(f"[{mode.upper()} MODE] Evaluating exam with {len(all_questions)} questions at exam-level")
        overall_result = await self.evaluate(exam, criteria, user_query)
        results["overall"] = overall_result
        
        # Track cumulative token usage
        total_prompt_tokens = overall_result.get("prompt_tokens", 0)
        total_completion_tokens = overall_result.get("completion_tokens", 0)
        model_name = overall_result.get("model_name", "unknown")
        
        # 2. Per-question evaluation (comprehensive mode only)
        if mode == "comprehensive":
            logger.info(f"[COMPREHENSIVE MODE] Evaluating all {len(all_questions)} questions individually")
            
            # Create evaluation tasks for all questions (concurrent)
            eval_tasks = []
            for q in all_questions:
                single_q = {
                    "type": "multiple_choice",
                    "questions": [q]
                }
                # Pass rag_content to individual questions too
                if rag_content:
                    single_q["rag_content"] = rag_content
                eval_tasks.append(self.evaluate(single_q, criteria, user_query))
            
            # Execute all evaluations concurrently
            question_results = await asyncio.gather(*eval_tasks, return_exceptions=True)
            
            # Format results
            results["per_question"] = []
            for i, (q, q_result) in enumerate(zip(all_questions, question_results)):
                if isinstance(q_result, Exception):
                    logger.error(f"Error evaluating question {q.get('question_number', i+1)}: {q_result}")
                    results["per_question"].append({
                        "question_type": q.get("question_type", "unknown"),
                        "question_number": q.get("question_number", i + 1),
                        "error": str(q_result),
                        "evaluations": []
                    })
                else:
                    results["per_question"].append({
                        "question_type": q.get("question_type", "unknown"),
                        "question_number": q.get("question_number", i + 1),
                        "evaluations": q_result.get("evaluations", [])
                    })
                    # Add tokens from individual question evaluations
                    total_prompt_tokens += q_result.get("prompt_tokens", 0)
                    total_completion_tokens += q_result.get("completion_tokens", 0)
            
            # Compute statistics
            results["statistics"] = self._compute_exam_statistics(results["per_question"])
        else:
            logger.info(f"[QUICK MODE] Skipping per-question evaluation")
            results["per_question"] = []
            results["statistics"] = {
                "note": f"Per-question evaluation skipped in {mode} mode"
            }
        
        # Include total usage
        results["prompt_tokens"] = total_prompt_tokens
        results["completion_tokens"] = total_completion_tokens
        results["model_name"] = model_name
        
        return results
    
    async def evaluate_single_question(
        self,
        question: Dict[str, Any],
        rag_content: str = None,
        criteria: List[str] = None,
        user_query: str = ""
    ) -> Dict[str, Any]:
        """
        Evaluate a single question.
        
        This is a simplified API for unit testing individual questions.
        
        Args:
            question: Single question dict with structure:
                {
                    "question_number": 1,
                    "question_text": "...",
                    "options": {"A": "...", "B": "..."},
                    "correct_answer": "A",
                    "source": {"page_number": "...", "evidence": "..."}
                }
            rag_content: Optional RAG context (retrieved educational material)
            criteria: List of criteria names to evaluate. If None, evaluates all rubrics.
        
        Returns:
            Dict with evaluation results for the single question
        
        Example:
            result = await critic.evaluate_single_question(question, rag_content="...")
        """
        # Wrap question in expected format
        content = {
            "type": "multiple_choice",
            "questions": [question]
        }
        
        # Add rag_content if provided
        if rag_content:
            content["rag_content"] = rag_content
        
        # Evaluate using the core evaluate method
        return await self.evaluate(content, criteria, user_query)
    
    def _compute_exam_statistics(self, per_question_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Compute summary statistics from per-question evaluation results.
        
        Args:
            per_question_results: List of per-question evaluation results
        
        Returns:
            Dict containing statistics:
            {
                "total_questions": int,
                "avg_scores_by_criteria": {"Understandable": 3.5, ...},
                "min_scores_by_criteria": {"Understandable": 2, ...},
                "max_scores_by_criteria": {"Understandable": 5, ...},
                "questions_below_threshold": [1, 3, 5]  # Question numbers
            }
        """
        if not per_question_results:
            return {}
        
        # Aggregate scores by criteria
        criteria_scores = {}
        questions_below_threshold = []
        
        for q_result in per_question_results:
            if "error" in q_result or not q_result.get("evaluations"):
                continue
            
            question_num = q_result.get("question_number")
            has_low_score = False
            
            for eval_item in q_result["evaluations"]:
                criteria = eval_item.get("criteria")
                rating = eval_item.get("rating", 0)
                
                if criteria:
                    if criteria not in criteria_scores:
                        criteria_scores[criteria] = []
                    criteria_scores[criteria].append(rating)
                
                # Check if any score is below threshold
                if rating < self.threshold:
                    has_low_score = True
            
            if has_low_score and question_num:
                questions_below_threshold.append(question_num)
        
        # Compute statistics
        stats = {
            "total_questions": len(per_question_results),
            "avg_scores_by_criteria": {},
            "min_scores_by_criteria": {},
            "max_scores_by_criteria": {},
            "questions_below_threshold": questions_below_threshold
        }
        
        for criteria, scores in criteria_scores.items():
            if scores:
                stats["avg_scores_by_criteria"][criteria] = round(sum(scores) / len(scores), 2)
                stats["min_scores_by_criteria"][criteria] = min(scores)
                stats["max_scores_by_criteria"][criteria] = max(scores)
        
        return stats
