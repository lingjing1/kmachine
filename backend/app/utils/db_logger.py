"""
Utility functions for logging orchestration and agent task data to the database.
"""
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Union, Callable
from sqlalchemy import Table, insert, update, select, func, text, Column, Integer, String, DateTime
import os
from dotenv import load_dotenv
import json
import logging

from backend.app.db import engine, metadata
from contextvars import ContextVar

# ContextVar to store environmental impact from the latest LLM call in the current context
current_environmental_impact: ContextVar[Optional[Dict[str, Any]]] = ContextVar("current_environmental_impact", default=None)

from backend.app.utils.time_utils import get_now_taipei, TAIPEI_TZ
USD_TO_TWD = 32.0
load_dotenv()

logger = logging.getLogger(__name__)

# --- EcoLogits Initialization ---
try:
    # Suppress ecologits warning logs that clutter the console
    logging.getLogger("ecologits").setLevel(logging.ERROR)
    
    from ecologits import EcoLogits
    EcoLogits.init(providers=["openai", "anthropic"])
    
    # --- Monkeypatch EcoLogits for OpenAI v2 / LegacyAPIResponse compatibility ---
    try:
        from ecologits.tracers import openai_tracer
        import time
        from ecologits.tracers.utils import llm_impacts, ImpactsOutput
        
        def patched_openai_chat_wrapper_non_stream(wrapped, instance, args, kwargs):
            timer_start = time.perf_counter()
            response = wrapped(*args, **kwargs)
            request_latency = time.perf_counter() - timer_start
            
            # OpenAI v1/v2 compatibility: handle LegacyAPIResponse
            target_response = response
            is_legacy = False
            if hasattr(response, 'parse') and not hasattr(response, 'model'):
                target_response = response.parse()
                is_legacy = True
            
            model_name = getattr(target_response, 'model', 'unknown')
            usage = getattr(target_response, 'usage', None)
            completion_tokens = getattr(usage, 'completion_tokens', 0) if usage else 0
            prompt_tokens = getattr(usage, 'prompt_tokens', 0) if usage else 0

            impacts = llm_impacts(
                provider=openai_tracer.PROVIDER,
                model_name=model_name,
                output_token_count=completion_tokens,
                request_latency=request_latency,
                electricity_mix_zone=EcoLogits.config.electricity_mix_zone
            )
            
            if impacts is not None:
                impact_dict = {
                    "carbon_g": impacts.gwp.value.mean * 1000,
                    "energy_kwh": impacts.energy.value.mean,
                    "water_l": impacts.wcf.value.mean,
                    "adpe_kgseb": impacts.adpe.value.mean,
                    "pe_mj": impacts.pe.value.mean
                }
                current_environmental_impact.set(impact_dict)

                if EcoLogits.config.opentelemetry:
                    EcoLogits.config.opentelemetry.record_request(
                        input_tokens=prompt_tokens,
                        output_tokens=completion_tokens,
                        request_latency=request_latency,
                        impacts=impacts,
                        provider=openai_tracer.PROVIDER,
                        model=model_name,
                        endpoint="/chat/completions"
                    )
                
                # If it was legacy, we can't easily wrap it back without breaking downstream
                # but ecologits usually returns a wrapped ChatCompletion.
                # For legacy, we just add the 'impacts' attribute to the original response if possible
                if is_legacy:
                    response.impacts = impacts
                    return response
                
                return openai_tracer.ChatCompletion(**target_response.model_dump(), impacts=impacts)
            return response

        openai_tracer.openai_chat_wrapper_non_stream = patched_openai_chat_wrapper_non_stream

        async def patched_openai_async_chat_wrapper_base(wrapped, instance, args, kwargs):
            timer_start = time.perf_counter()
            response = await wrapped(*args, **kwargs)
            request_latency = time.perf_counter() - timer_start
            
            target_response = response
            is_legacy = False
            if hasattr(response, 'parse') and not hasattr(response, 'model'):
                target_response = response.parse()
                is_legacy = True
            
            model_name = getattr(target_response, 'model', 'unknown')
            usage = getattr(target_response, 'usage', None)
            completion_tokens = getattr(usage, 'completion_tokens', 0) if usage else 0
            prompt_tokens = getattr(usage, 'prompt_tokens', 0) if usage else 0

            impacts = llm_impacts(
                provider=openai_tracer.PROVIDER,
                model_name=model_name,
                output_token_count=completion_tokens,
                request_latency=request_latency,
                electricity_mix_zone=EcoLogits.config.electricity_mix_zone
            )
            
            if impacts is not None:
                impact_dict = {
                    "carbon_g": impacts.gwp.value.mean * 1000,
                    "energy_kwh": impacts.energy.value.mean,
                    "water_l": impacts.wcf.value.mean,
                    "adpe_kgseb": impacts.adpe.value.mean,
                    "pe_mj": impacts.pe.value.mean
                }
                current_environmental_impact.set(impact_dict)
                
                if EcoLogits.config.opentelemetry:
                    EcoLogits.config.opentelemetry.record_request(
                        input_tokens=prompt_tokens,
                        output_tokens=completion_tokens,
                        request_latency=request_latency,
                        impacts=impacts,
                        provider=openai_tracer.PROVIDER,
                        model=model_name,
                        endpoint="/chat/completions"
                    )
                
                if is_legacy:
                    response.impacts = impacts
                    return response
                
                return openai_tracer.ChatCompletion(**target_response.model_dump(), impacts=impacts)
            return response

        openai_tracer.openai_async_chat_wrapper_base = patched_openai_async_chat_wrapper_base
        logger.info("EcoLogits monkeypatched for LegacyAPIResponse (Sync & Async) compatibility.")
    except Exception as me:
        logger.warning(f"Failed to monkeypatch EcoLogits: {me}")

    logger.info("EcoLogits initialized for environmental tracking.")
except ImportError:
    pass
except Exception as e:
    logger.warning(f"Failed to initialize EcoLogits: {e}")

# --- Metadata ---
AGENT_METADATA = {
    # --- Orchestration & Routing (流程調度與分發) ---
    "teacher_agent_router": {"desc": "正在分析您的教學需求...", "purpose": "分析教師需求並分發至對應的教學技能子系統（生成、總結、對話）", "avatar": "planner.png"},
    "refinement_orchestrator": {"desc": "正在分析如何優化內容...", "purpose": "在手動編輯或自動反饋流程中，協調舊內容與新反饋的整合流程", "avatar": "planner.png"},

    # --- Ingestion Agents (文件處理與向量化) ---
    "hash_file": {"desc": "正在檢查文件是否曾經上傳...", "purpose": "確保文件唯一性並檢查是否重複上傳"},
    "delete_old_content": {"desc": "正在清理舊有向量資料...", "purpose": "重新處理時移除資料庫中的舊有結構與向量資料"},
    "link_material": {"desc": "正在設定文件與課程的關聯...", "purpose": "將文件與特定課程及單元進行權限與歸屬綁定"},
    "document_loader": {"desc": "正在提取文件中的文字與結構...", "purpose": "解析多種格式文件並提取乾淨的文字與圖片資料"},
    "database_writer": {"desc": "正在存儲文件中的文字資料...", "purpose": "將解析後的分頁內容與多模態資料存入資料庫"},
    "vision_llm": {"desc": "正在理解文件中的圖片...", "purpose": "使用視覺模型描述教材中的圖像、圖表與公式內容"},
    "text_splitter": {"desc": "正在切分文件中的文字資料...", "purpose": "根據教學邏輯與長度限制將教材拆解為檢索片段"},
    "embedding_generator": {"desc": "正在將文件中的文字資料向量化...", "purpose": "將文本轉換為數字向量並存入向量資料庫以供後續檢索"},
    "finalize_status": {"desc": "正在完成文件處理程序...", "purpose": "標記文件處理完成並啟動正式使用權限"},

    # --- Knowledge Point Agents (知識點提取) ---
    "kp_extractor": {"desc": "正在分析教材中的核心知識點...", "purpose": "從教材中自動分析並識別核心知識點及其架構", "avatar": "planner.png"},

    # --- Generator Agents (教學內容生成) ---
    "retriever": {"desc": "正在檢索最相關的參考資料片段...", "purpose": "從資料庫中提取最相關的教材片段提供事實依據", "avatar": "retriever.png"},
    "plan_generation_tasks": {"desc": "正在規劃題目生成流程...", "purpose": "將複雜請求拆解為具體的生成步驟與題型清單", "avatar": "planner.png"},
    "generate_multiple_choice": {"desc": "正在設計綜合選擇題...", "purpose": "根據教材內容產生高品質選擇題", "avatar": "quiz_master.png"},
    "generate_short_answer": {"desc": "正在構思啟發性簡答題...", "purpose": "根據教材內容產生高品質簡答題", "avatar": "short_answer.png"},
    "generate_true_false": {"desc": "正在建立觀念是非題...", "purpose": "根據教材內容產生高品質是非題", "avatar": "true_false.png"},
    "generate_fill_in_blank": {"desc": "正在編寫重點填空題...", "purpose": "根據教材內容產生高品質填空題", "avatar": "fill_in_blank.png"},
    "summarizer": {"desc": "正在為您整理教材精華...", "purpose": "將長篇教材轉化為結構化的教學摘要", "avatar": "summarizer.png"},
    "general_chat_skill": {"desc": "正在思考如何回應您的詢問...", "purpose": "處理與特定功能無關的通用教學詢問", "avatar": "planner.png"},

    # --- Critic Agents (評核與反饋 - 只看不改) ---
    "fact_critic": {"desc": "正在核對內容與教材的事實一致性...", "purpose": "驗證生成內容是否符合教材事實且無虛假陳述", "avatar": "retriever.png"},
    "quality_critic": {"desc": "正在評估教學價值與品質...", "purpose": "從教學價值與邏輯性進行評分", "avatar": "planner.png"},

    # --- Refinement Agents ---
    "refine_exam": {"desc": "正在根據反饋優化內容...", "purpose": "接收審查反饋，自動優化並修正已生成的題目內容", "avatar": "planner.png"},

    # --- Persistence Agents (資產化儲存) ---
    "course_content_saver": {"desc": "正在將生成成果存儲至資料庫...", "purpose": "正在將生成結果存儲為正式教材、Embedding 向量化並建立 RAG 索引", "avatar": "retriever.png"},

}

# --- Console Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='[COOK-AI] %(asctime)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger.setLevel(logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING) # Suppress noisy HTTP logs from OpenAI client

# --- Table Reflection ---
try:
    import warnings
    from sqlalchemy.exc import SAWarning
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', 'Did not recognize type', SAWarning)
        metadata.reflect(bind=engine)
    
    orchestration_jobs = Table('orchestration_jobs', metadata, autoload_with=engine)
    agent_tasks = Table('agent_tasks', metadata, autoload_with=engine)
    generated_contents = Table('generated_contents', metadata, autoload_with=engine)
    agent_task_sources = Table('agent_task_sources', metadata, autoload_with=engine)
    reference_feedbacks = Table('reference_feedbacks', metadata, autoload_with=engine)
    generator_setting_logs = Table('generator_setting_logs', metadata, autoload_with=engine)
    exp_seed_configs = Table('exp_seed_configs', metadata, autoload_with=engine)
    exp_generated_contents = Table('exp_generated_contents', metadata, autoload_with=engine)
except Exception as e:
    logger.error(f"Error reflecting database tables: {e}")
    import sqlalchemy as sa
    from sqlalchemy.dialects import postgresql
    
    orchestration_jobs = Table('orchestration_jobs', metadata,
        Column('id', Integer, primary_key=True),
        Column('user_id', Integer),
        Column('status', String),
        Column('input_config', postgresql.JSONB),
        Column('final_output_id', Integer),
        Column('total_iterations', Integer),
        Column('total_prompt_tokens', Integer),
        Column('total_completion_tokens', Integer),
        Column('total_latency_ms', Integer),
        Column('total_cost_usd', sa.Numeric),
        Column('total_cost_twd', sa.Numeric),
        Column('used_models', postgresql.JSONB),
        Column('environmental_impact', postgresql.JSONB),
        Column('error_message', String),
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
    )
    agent_tasks = Table('agent_tasks', metadata,
        Column('id', Integer, primary_key=True),
        Column('job_id', Integer),
        Column('agent_name', String),
        Column('status', String),
        Column('output', sa.JSON if not hasattr(postgresql, 'JSONB') else postgresql.JSONB),
        Column('model_parameters', sa.JSON if not hasattr(postgresql, 'JSONB') else postgresql.JSONB),
        Column('estimated_cost_usd', sa.Numeric),
        Column('environmental_impact', postgresql.JSONB),
    )
    # ... other tables similarly

import functools


def _update_task_iteration_sync(task_id: int, new_iteration: int, initial_iteration: int):
    """
    Synchronous helper to update the iteration number in the database.
    Designed to be run in a thread pool.
    """
    try:
        with engine.connect() as conn:
            stmt = update(agent_tasks).where(
                agent_tasks.c.id == task_id
            ).values(iteration_number=new_iteration)
            conn.execute(stmt)
            conn.commit()
            logger.info(f"✅ Updated task {task_id} iteration_number from {initial_iteration} to {new_iteration}")
    except Exception as e:
        logger.warning(f"Failed to update iteration_number for task {task_id}: {e}")

# --- Decorator for Task Logging ---

# --- Data Scrubbing Utility ---

def _scrub_data(data: Any, max_size_kb: int = 20) -> Any:
    """
    Minimizes storage by removing large buffers or context from inputs/outputs.
    If it's a list of chunks, extracts the IDs instead of full text.
    """
    if data is None:
        return None
        
    if isinstance(data, dict):
        new_dict = {}
        for k, v in data.items():
            # 1. Handle Retriever Chunks specifically
            if k in ['retrieved_text_chunks', 'retrieved_page_content'] and isinstance(v, list):
                try:
                    # Extract IDs only
                    extracted_ids = []
                    for c in v:
                        if not isinstance(c, dict): continue
                        
                        cid = c.get("chunk_id") or c.get("id")
                        if cid:
                            extracted_ids.append(str(cid))
                        elif c.get("type") == "structured_page_content":
                            # For full page content, use doc_id + page_num as identifier
                            doc_id = c.get("source_document_id")
                            p_num = c.get("page_number")
                            extracted_ids.append(f"doc_{doc_id}_p{p_num}")
                        else:
                            extracted_ids.append("null")
                            
                    new_dict[k] = f"[SUMMARY: {len(v)} items. IDs: {extracted_ids}]"
                except Exception:
                    new_dict[k] = f"[SUMMARY: {len(v)} items (ID extract failed)]"
                continue

            # 2. Aggressive scrubbing of source text in nested structures (citations, source inside questions)
            is_redundant_key = k in ['citations', 'source']
            if is_redundant_key and isinstance(v, list):
                scrubbed_list = []
                for cit in v:
                    if isinstance(cit, dict):
                        # Use internal recurse to clean but apply aggressive text removal here
                        c_copy = {k2: v2 for k2, v2 in cit.items() if k2 not in ['text', 'combined_human_text', 'source_metadata', 'combined_content']}
                        if 'source_metadata' in cit and isinstance(cit['source_metadata'], dict):
                            c_copy['source_name'] = cit['source_metadata'].get('document_name', cit.get('source'))
                        scrubbed_list.append(c_copy)
                new_dict[k] = scrubbed_list
                continue
            elif is_redundant_key and isinstance(v, dict):
                # Keep essentials, drop big text
                new_dict[k] = {k2: v2 for k2, v2 in v.items() if k2 not in ['text', 'combined_human_text', 'source_metadata', 'combined_content']}
                if 'source_metadata' in v and isinstance(v['source_metadata'], dict):
                    new_dict[k]['source_name'] = v['source_metadata'].get('document_name')
                continue

            # 3. General Scrubbing for large strings/lists
            if isinstance(v, (dict, list, str)):
                v_str = str(v)
                if len(v_str) > max_size_kb * 1024:
                    # Recursive scrub for important list/dict keys
                    if k in ['exam_data', 'questions', 'sections', 'final_generated_content'] or isinstance(v, (dict, list)):
                        new_dict[k] = _scrub_data(v, max_size_kb)
                    else:
                        new_dict[k] = f"[REDACTED: Large Data ({len(v_str)//1024}KB)]"
                else:
                    new_dict[k] = _scrub_data(v, max_size_kb)
            else:
                new_dict[k] = v
        return new_dict
    elif isinstance(data, list):
        if len(data) > 15: # Limit list size for logging
             return [_scrub_data(i, max_size_kb) for i in data[:10]] + [f"... (total {len(data)} items)"]
        return [_scrub_data(i, max_size_kb) for i in data]
    return data

def log_task(agent_name: str, input_extractor: Optional[Callable[[Dict], Dict]] = None):
    """
    Decorator for AI nodes in LangGraph.
    Automatically handles task creation, iteration tracking, and output logging.
    """
    def decorator(func):
        # Check if function is async
        import asyncio
        import inspect
        is_async = asyncio.iscoroutinefunction(func)
        
        if is_async:
            # Async wrapper
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs) -> Any:
                # Import here to avoid circular imports
                from backend.app.utils.concurrency import run_in_db_pool

                # Handle both state (Dict) and normal arguments
                is_langgraph = args and isinstance(args[0], dict)
                state = args[0] if is_langgraph else {}

                # Determine task_input
                extracted_task_input = None
                if input_extractor:
                    try:
                        extracted_task_input = input_extractor(*args, **kwargs)
                    except Exception as e:
                        logger.warning(f"Failed to extract task input for '{agent_name}': {e}")
                        extracted_task_input = {"user_query": state.get("user_query")}
                else:
                    extracted_task_input = {"user_query": state.get("user_query", "Unknown Task")}

                # Get job_id
                job_id = state.get('job_id') or kwargs.get('job_id')
                if not job_id:
                    # If no job_id, just call without logging
                    return await func(*args, **kwargs)

                task_id = await run_in_db_pool(
                    create_task,
                    job_id=job_id,
                    agent_name=agent_name,
                    task_input=extracted_task_input,
                    parent_task_id=state.get("current_task_id") or state.get("parent_task_id") or kwargs.get("current_task_id"),
                    iteration_number=state.get("iteration_count", 1) or kwargs.get("iteration_count", 1)
                )
                
                if task_id is None:
                    return await func(*args, **kwargs)

                start_time = time.perf_counter()
                initial_iteration = state.get("iteration_count", 1) or kwargs.get("iteration_count", 1)
                
                try:
                    # Prepare arguments
                    if is_langgraph:
                        state_for_node = state.copy()
                        state_for_node['current_task_id'] = task_id
                        new_args = list(args)
                        new_args[0] = state_for_node
                        result = await func(*new_args, **kwargs)
                    else:
                        result = await func(*args, **kwargs)
                    
                    duration_ms = int((time.perf_counter() - start_time) * 1000)
                    
                    # Handle iteration increase (if dict)
                    new_iteration = initial_iteration
                    if isinstance(result, dict):
                        new_iteration = result.get("iteration_count", initial_iteration)
                    
                    if new_iteration != initial_iteration:
                        await run_in_db_pool(
                            _update_task_iteration_sync,
                            task_id=task_id,
                            new_iteration=new_iteration,
                            initial_iteration=initial_iteration
                        )
                    
                    # Log completion
                    router_output = None
                    if isinstance(result, dict):
                        router_output = result.pop("_router_output", None)
                    
                    metrics = {}
                    if isinstance(result, dict):
                        metrics = {
                            "prompt_tokens": result.get("prompt_tokens"),
                            "completion_tokens": result.get("completion_tokens"),
                            "estimated_cost_usd": result.get("estimated_cost_usd"),
                            "model_name": result.get("model_name"),
                            "environmental_impact": result.get("environmental_impact")
                        }

                    db_output = router_output or result
                    await run_in_db_pool(
                        update_task,
                        task_id, 'completed', 
                        output=db_output, 
                        duration_ms=duration_ms,
                        **metrics
                    )
                    
                    if is_langgraph:
                        final_result = state.copy()
                        if isinstance(result, dict):
                            final_result.update(result)
                        else:
                            final_result["_output"] = result
                        
                        if "error" not in final_result:
                            final_result["current_task_id"] = task_id
                        return final_result
                    else:
                        return result

                except Exception as e:
                    error_message = str(e)
                    duration_ms = int((time.perf_counter() - start_time) * 1000)
                    await run_in_db_pool(
                        update_task, 
                        task_id, 'failed', 
                        error_message=error_message, 
                        duration_ms=duration_ms
                    )
                    raise e
            
            return async_wrapper
        
        else:
            # Sync wrapper (original implementation)
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs) -> Any:
                # Handle both state (Dict) and normal arguments
                is_langgraph = args and isinstance(args[0], dict)
                state = args[0] if is_langgraph else {}

                # Determine task_input
                extracted_task_input = None
                if input_extractor:
                    try:
                        extracted_task_input = input_extractor(*args, **kwargs)
                    except Exception as e:
                        logger.warning(f"Failed to extract task input for '{agent_name}': {e}")
                        extracted_task_input = {"user_query": state.get("user_query")}
                else:
                    extracted_task_input = {"user_query": state.get("user_query", "Unknown Task")}

                # Get job_id
                job_id = state.get('job_id') or kwargs.get('job_id')
                if not job_id:
                    return func(*args, **kwargs)

                task_id = create_task(
                    job_id=job_id,
                    agent_name=agent_name,
                    task_input=extracted_task_input,
                    parent_task_id=state.get("current_task_id") or state.get("parent_task_id") or kwargs.get("current_task_id"),
                    iteration_number=state.get("iteration_count", 1) or kwargs.get("iteration_count", 1)
                )
                
                if task_id is None:
                    return func(*args, **kwargs)

                start_time = time.perf_counter()
                initial_iteration = state.get("iteration_count", 1) or kwargs.get("iteration_count", 1)
                
                try:
                    # Prepare arguments
                    if is_langgraph:
                        state_for_node = state.copy()
                        state_for_node['current_task_id'] = task_id
                        new_args = list(args)
                        new_args[0] = state_for_node
                        result = func(*new_args, **kwargs)
                    else:
                        result = func(*args, **kwargs)
                    
                    duration_ms = int((time.perf_counter() - start_time) * 1000)
                    
                    # Handle iteration (if dict)
                    new_iteration = initial_iteration
                    if isinstance(result, dict):
                        new_iteration = result.get("iteration_count", initial_iteration)
                    
                    if new_iteration != initial_iteration:
                        try:
                            with engine.connect() as conn:
                                stmt = update(agent_tasks).where(
                                    agent_tasks.c.id == task_id
                                ).values(iteration_number=new_iteration)
                                conn.execute(stmt)
                                conn.commit()
                        except Exception as e:
                            logger.warning(f"Failed to update iteration_number for task {task_id}: {e}")
                    
                    # Log completion
                    router_output = None
                    if isinstance(result, dict):
                        router_output = result.pop("_router_output", None)
                    
                    metrics = {}
                    if isinstance(result, dict):
                        metrics = {
                            "prompt_tokens": result.get("prompt_tokens"),
                            "completion_tokens": result.get("completion_tokens"),
                            "estimated_cost_usd": result.get("estimated_cost_usd"),
                            "model_name": result.get("model_name"),
                            "environmental_impact": result.get("environmental_impact")
                        }

                    db_output = router_output or result
                    update_task(
                        task_id, 'completed', 
                        output=db_output, 
                        duration_ms=duration_ms,
                        **metrics
                    )
                    
                    if is_langgraph:
                        final_result = state.copy()
                        if isinstance(result, dict):
                            final_result.update(result)
                        else:
                            final_result["_output"] = result
                        
                        if "error" not in final_result:
                            final_result["current_task_id"] = task_id
                        return final_result
                    else:
                        return result

                except Exception as e:
                    error_message = str(e)
                    duration_ms = int((time.perf_counter() - start_time) * 1000)
                    update_task(task_id, 'failed', error_message=error_message, duration_ms=duration_ms)
                    raise e
            
            return sync_wrapper
    
    return decorator

# --- Job-level Logging ---

def create_job(user_id: int, input_prompt: str, workflow_type: str, experiment_config: Optional[Dict] = None, job_context: Optional[Dict] = None) -> Optional[int]:
    """Creates a new record in the orchestration_jobs table."""
    try:
        with engine.connect() as conn:
            stmt = insert(orchestration_jobs).values(
                user_id=user_id,
                status='planning',
                input_config={
                    "original_prompt": input_prompt,
                    "workflow_type": workflow_type,
                    "experiment_config": experiment_config or {},
                    "job_context": job_context or {}
                } if not experiment_config and not job_context else {
                    "original_prompt": input_prompt,
                    "workflow_type": workflow_type,
                    "experiment_config": experiment_config or {},
                    "job_context": job_context or {}
                },
                created_at=get_now_taipei(),
                updated_at=get_now_taipei()
            ).returning(orchestration_jobs.c.id)
            result = conn.execute(stmt)
            job_id = result.scalar_one()
            conn.commit()
            logger.info(f"\n{'='*20} 🟢 JOB START: {job_id} ({workflow_type}) {'='*20}")
            return job_id
    except Exception as e:
        logger.error(f"Failed to create job. Reason: {e}")
        return None

def update_job_status(job_id: int, status: str, error_message: Optional[str] = None):
    """Updates the status and error message of a job with idempotency check for logs."""
    try:
        with engine.connect() as conn:
            # 1. Fetch current status to avoid redundant terminal logging
            current_status = conn.execute(
                select(orchestration_jobs.c.status).where(orchestration_jobs.c.id == job_id)
            ).scalar_one_or_none()
            
            if current_status == status:
                return # No change, skip

            # 2. Update status
            stmt = update(orchestration_jobs).where(orchestration_jobs.c.id == job_id).values(
                status=status,
                error_message=error_message,
                updated_at=get_now_taipei()
            )
            conn.execute(stmt)
            conn.commit()
            
            # 3. Log banner only for transitions to terminal states
            if status in ['completed', 'failed']:
                symbol = "✅" if status == 'completed' else "❌"
                logger.info(f"\n{'='*20} {symbol} JOB {status.upper()}: {job_id} {'='*20}")
            else:
                logger.info(f"Job {job_id}: Status updated to '{status}'")
        
        # 4. Automatically update cumulative metrics only once on completion
        if status == 'completed' and current_status != 'completed':
            update_job_iterations_and_cost(job_id)
            
    except Exception as e:
        logger.error(f"Failed to update job {job_id}. Reason: {e}")

def update_job_final_output(job_id: int, final_output_id: int):
    """Updates the final_output_id of a job."""
    try:
        with engine.connect() as conn:
            stmt = update(orchestration_jobs).where(orchestration_jobs.c.id == job_id).values(
                final_output_id=final_output_id,
                updated_at=get_now_taipei()
            )
            conn.execute(stmt)
            conn.commit()
            logger.info(f"Updated job {job_id} with final_output_id: {final_output_id}.")
    except Exception as e:
        logger.error(f"Failed to update job {job_id} final_output_id. Reason: {e}")

def update_job_context(job_id: int, context_updates: Dict[str, Any]):
    """
    Updates the job_context within the input_config of a job.
    Merges updates into existing job_context.
    """
    try:
        with engine.connect() as conn:
            # 1. Fetch current input_config
            stmt = select(orchestration_jobs.c.input_config).where(orchestration_jobs.c.id == job_id)
            current_config = conn.execute(stmt).scalar_one_or_none()
            
            if not current_config:
                logger.warning(f"No job found to update context for ID {job_id}")
                return
            
            # 2. Extract and update job_context
            job_context = current_config.get("job_context", {})
            job_context.update(context_updates)
            
            # 3. Create new input_config dict
            new_config = dict(current_config)
            new_config["job_context"] = job_context
            
            # 4. Update back to DB
            update_stmt = update(orchestration_jobs).where(orchestration_jobs.c.id == job_id).values(
                input_config=new_config,
                updated_at=get_now_taipei()
            )
            conn.execute(update_stmt)
            conn.commit()
            logger.info(f"Job {job_id}: Context updated with {list(context_updates.keys())}")
            
    except Exception as e:
        logger.error(f"Failed to update job {job_id} context. Reason: {e}")

def get_job_status(job_id: int) -> Optional[str]:
    """Retrieves the current status of a job."""
    try:
        with engine.connect() as conn:
            stmt = select(orchestration_jobs.c.status).where(orchestration_jobs.c.id == job_id)
            status = conn.execute(stmt).scalar_one_or_none()
            return status
    except Exception as e:
        logger.error(f"Failed to get status for job {job_id}. Reason: {e}")
        return None

# --- Task-level Logging ---

def create_task(
    job_id: int, 
    agent_name: str, 
    task_input: Optional[Dict] = None, 
    model_name: Optional[str] = None, 
    parent_task_id: Optional[int] = None, 
    model_parameters: Optional[Dict] = None,
    iteration_number: int = 1
) -> Optional[int]:
    """Creates a new record in the agent_tasks table and returns its ID."""
    try:
        with engine.connect() as conn:
            stmt = insert(agent_tasks).values(
                job_id=job_id,
                agent_name=agent_name,
                task_input=_scrub_data(task_input),
                status='in_progress',
                model_name=model_name,
                parent_task_id=parent_task_id,
                model_parameters=model_parameters,
                iteration_number=iteration_number,
                created_at=get_now_taipei()
            ).returning(agent_tasks.c.id)
            result = conn.execute(stmt)
            task_id = result.scalar_one()
            conn.commit()
            agent_desc = AGENT_METADATA.get(agent_name, {}).get("desc", agent_name)
            logger.info(f"Task {task_id}: {agent_desc} (Job {job_id})")
            return task_id
    except Exception as e:
        logger.error(f"Failed to create task for agent '{agent_name}'. Reason: {e}")
        return None

def update_task(
    task_id: int,
    status: str,
    output: Optional[Any] = None, # Changed type hint to Any
    error_message: Optional[str] = None,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    duration_ms: Optional[int] = None,
    estimated_cost_usd: Optional[float] = None,
    model_name: Optional[str] = None,
    model_parameters: Optional[Dict] = None,
    environmental_impact: Optional[Dict] = None
):
    """Updates an agent_task record upon completion or failure."""
    # Check ContextVar if not provided
    auto_impact = current_environmental_impact.get()
    if environmental_impact is None and auto_impact is not None:
        environmental_impact = auto_impact
        current_environmental_impact.set(None) # Clear for next call

    try:
        with engine.connect() as conn:
            processed_output = None
            if output is not None:
                if isinstance(output, (dict, list)):
                    processed_output = output
                elif isinstance(output, str):
                    try:
                        processed_output = json.loads(output)
                    except json.JSONDecodeError:
                        processed_output = {"text_output": output} # Wrap plain strings
                else:
                    processed_output = {"value": str(output)} # Catch all other types

            values = { # Renamed from values_to_update to values as per snippet
                "status": status,
                "output": _scrub_data(processed_output), # ✅ Apply scrubbing to output
                "error_message": error_message,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "duration_ms": duration_ms,
                "completed_at": datetime.now(TAIPEI_TZ).replace(tzinfo=None),
                "estimated_cost_usd": estimated_cost_usd,
                "model_name": model_name,
                "model_parameters": model_parameters,
                "environmental_impact": environmental_impact
            }
            # Filter out None values so they don't overwrite existing data in the DB
            values = {k: v for k, v in values.items() if v is not None}
            


            stmt = update(agent_tasks).where(agent_tasks.c.id == task_id).values(**values)
            conn.execute(stmt)
            conn.commit()
            # logger.info(f"✅ Task {task_id}: Completed")  # User requested to skip completion logs
    except Exception as e:
        logger.error(f"Failed to update task {task_id}. Reason: {e}")


# --- Content and Source Logging ---

def log_task_sources(task_id: int, source_chunks: Optional[List[Dict]] = None):
    """Logs the retrieved source chunks for a specific task."""
    if not source_chunks:
        return

    try:
        with engine.connect() as conn:
            records_to_insert = []
            for chunk in source_chunks:
                chunk_id_raw = chunk.get("chunk_id")
                if chunk_id_raw is None:
                    continue
                
                # Default values
                source_type = 'chunk'
                source_id = chunk_id_raw
                
                # Handle RAG prefixed IDs (doc_123, gen_456)
                if isinstance(chunk_id_raw, str):
                    try:
                        if chunk_id_raw.startswith("doc_"):
                            source_type = "document_chunk"
                            source_id = int(chunk_id_raw.replace("doc_", ""))
                        elif chunk_id_raw.startswith("gen_"):
                            source_type = "generated_chunk"
                            source_id = int(chunk_id_raw.replace("gen_", ""))
                        else:
                            # Try parsing as plain int if it's a string number
                            source_id = int(chunk_id_raw)
                    except ValueError:
                         logger.warning(f"Skipping source log for invalid ID format: {chunk_id_raw}")
                         continue
                
                records_to_insert.append({
                    "job_id": job_id_query(task_id, conn), # Generic helper to get job_id
                    "task_id": task_id,
                    "source_type": source_type,
                    "source_id": source_id
                })
            
            if not records_to_insert:
                return

            # Use PostgreSQL-specific insert for on_conflict_do_nothing
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            for record in records_to_insert:
                stmt = pg_insert(agent_task_sources).values(**record).on_conflict_do_nothing()
                conn.execute(stmt)
            conn.commit()
            
            logger.info(f"Logged {len(records_to_insert)} sources for task {task_id}.")

    except Exception as e:
        logger.error(f"Failed to log sources for task {task_id}. Reason: {e}")


def save_generated_content(task_id: int, content_type: str, title: str, content: str, author_id: Optional[int] = None) -> Optional[int]:
    """Saves generated content to the GENERATED_CONTENTS table."""
    try:
        with engine.connect() as conn:
            # The 'content' column in the DB is JSON. Parse the incoming JSON string if needed.
            if isinstance(content, str):
                try:
                    parsed_content = json.loads(content)
                except json.JSONDecodeError:
                     # If not valid JSON, treat as plain text wrapped in dict
                    parsed_content = {"text_content": content}
            elif isinstance(content, list):
                # ✅ FIX: Handle list directly (e.g., exam questions array)
                parsed_content = content
            elif isinstance(content, dict):
                parsed_content = content
            else:
                parsed_content = {"value": content}

            # ✅ FIX: Only inject 'type' if it doesn't exist to preserve material_type and other metadata
            # Skills like summarization already include 'type' and 'material_type' in their output
            if isinstance(parsed_content, dict):
                # Only set 'type' if not already present (preserve skill-generated structure)
                if 'type' not in parsed_content:
                    parsed_content["type"] = content_type
                # Also add display_type for UI rendering hints
                if 'display_type' not in parsed_content:
                    # Map content_type to display_type
                    display_type_map = {
                        'exam_questions': 'exam_questions',
                        'summary_report': 'summary_report',
                        'summary': 'summary_report'  # Map 'summary' to 'summary_report' for display
                    }
                    parsed_content['display_type'] = display_type_map.get(content_type, content_type)
            elif isinstance(parsed_content, list):
                # ✅ FIX: For exam questions (arrays), keep as array
                # Don't wrap in {type, display_type, data} structure
                # Frontend expects raw array for exam_questions
                pass  # Keep parsed_content as-is (array)
            else:
                # For other types (e.g., string, int), wrap it in a dict with the type
                parsed_content = {"type": content_type, "display_type": content_type, "value": parsed_content}
            
            # Prepare insert values
            values = {
                "source_agent_task_id": task_id,
                "content_type": content_type,
                "title": title,
                "content": parsed_content,
                "created_at": datetime.now(TAIPEI_TZ).replace(tzinfo=None),
                "updated_at": datetime.now(TAIPEI_TZ).replace(tzinfo=None)
            }
            
            # Add author_id if provided
            if author_id is not None:
                values["author_id"] = author_id

            stmt = insert(generated_contents).values(**values).returning(generated_contents.c.id)
            
            result = conn.execute(stmt)
            content_id = result.scalar_one()
            conn.commit()
            
            # Note: We don't call update_job_final_output here anymore
            # to keep this function atomic and avoid FK violations 
            # if called within another connection. The orchestrator (graph.py)
            # will handle linking the content to the job.
            
            logger.info(f"Saved generated content for task {task_id}. New content ID: {content_id}.")
            return content_id
            
    except Exception as e:
        logger.error(f"Failed to save generated content for task {task_id}. Reason: {e}")
        return None

def get_generated_content_by_id(content_id: int) -> Optional[Dict]:
    """Retrieves generated content by its ID from the GENERATED_CONTENTS table."""
    try:
        with engine.connect() as conn:
            stmt = select(generated_contents.c.content, generated_contents.c.title).where(generated_contents.c.id == content_id)
            result = conn.execute(stmt).fetchone()
            if result:
                return {"title": result.title, "data": result.content}
            return None
    except Exception as e:
        logger.error(f"Failed to retrieve generated content {content_id}. Reason: {e}")
        return None

def get_job_final_output_id(job_id: int) -> Optional[int]:
    """Retrieves the final_output_id for a given job_id from the orchestration_jobs table."""
    try:
        with engine.connect() as conn:
            stmt = select(orchestration_jobs.c.final_output_id).where(orchestration_jobs.c.id == job_id)
            result = conn.execute(stmt).scalar_one_or_none()
            return result
    except Exception as e:
        logger.error(f"Failed to retrieve final_output_id for job {job_id}. Reason: {e}")
        return None

def get_latest_iteration_number(job_id: int) -> int:
    """
    Retrieves the current maximum iteration number for a job.
    Returns 0 if no tasks exist for the job.
    """
    try:
        with engine.connect() as conn:
            stmt = select(func.max(agent_tasks.c.iteration_number)).where(agent_tasks.c.job_id == job_id)
            result = conn.execute(stmt).scalar()
            return int(result) if result is not None else 0
    except Exception as e:
        logger.error(f"Failed to get latest iteration number for job {job_id}. Reason: {e}")
        return 0

def get_task_iteration_number(task_id: int) -> int:
    """Retrieves the iteration number of a specific task."""
    try:
        with engine.connect() as conn:
            stmt = select(agent_tasks.c.iteration_number).where(agent_tasks.c.id == task_id)
            result = conn.execute(stmt).scalar()
            return int(result) if result is not None else 1
    except Exception as e:
        logger.error(f"Failed to get iteration number for task {task_id}. Reason: {e}")
        return 1

def get_job_cumulative_metrics(job_id: int) -> Optional[Dict[str, Any]]:
    """
    Retrieves cumulative metrics from all agent_tasks for a given job.
    
    Returns a dictionary with:
    - total_iterations: Count of distinct iteration_number values
    - total_prompt_tokens: Sum of all prompt_tokens
    - total_completion_tokens: Sum of all completion_tokens
    - total_latency_ms: Sum of all duration_ms
    - environmental_impact: Merged JSONB metrics from all tasks
    """
    try:
        with engine.connect() as conn:
            # Query to aggregate metrics
            stmt = select(
                func.count(func.distinct(agent_tasks.c.iteration_number)).label('total_iterations'),
                func.coalesce(func.sum(agent_tasks.c.prompt_tokens), 0).label('total_prompt_tokens'),
                func.coalesce(func.sum(agent_tasks.c.completion_tokens), 0).label('total_completion_tokens'),
                func.coalesce(func.sum(agent_tasks.c.duration_ms), 0).label('total_latency_ms')
            ).where(agent_tasks.c.job_id == job_id)
            
            result = conn.execute(stmt).fetchone()
            
            if result:
                # Get distinct models used in this job
                models_stmt = select(func.distinct(agent_tasks.c.model_name)).where(agent_tasks.c.job_id == job_id)
                models = [m for m in conn.execute(models_stmt).scalars() if m]
                
                # Sum total cost
                cost_stmt = select(func.sum(agent_tasks.c.estimated_cost_usd)).where(agent_tasks.c.job_id == job_id)
                total_usd = float(conn.execute(cost_stmt).scalar() or 0.0)

                # Aggregate environmental impact JSONB
                impact_stmt = select(agent_tasks.c.environmental_impact).where(
                    (agent_tasks.c.job_id == job_id) & (agent_tasks.c.environmental_impact != None)
                )
                all_impacts = conn.execute(impact_stmt).scalars().all()
                
                merged_impact = {
                    "carbon_g": 0.0,
                    "energy_kwh": 0.0,
                    "water_l": 0.0,
                    "adpe_kgseb": 0.0,
                    "pe_mj": 0.0
                }
                
                for impact in all_impacts:
                    if not impact: continue
                    for key in merged_impact:
                        merged_impact[key] += float(impact.get(key, 0.0))

                return {
                    "total_iterations": result.total_iterations or 0,
                    "total_prompt_tokens": int(result.total_prompt_tokens),
                    "total_completion_tokens": int(result.total_completion_tokens),
                    "total_latency_ms": int(result.total_latency_ms),
                    "total_cost_usd": total_usd,
                    "total_cost_twd": total_usd * USD_TO_TWD,
                    "used_models": models,
                    "environmental_impact": merged_impact
                }
            return None
    except Exception as e:
        logger.error(f"Failed to aggregate job {job_id} metrics. Reason: {e}")
        return None
            
def job_id_query(task_id: int, conn) -> int:
    """Helper to get job_id from task_id."""
    return conn.execute(select(agent_tasks.c.job_id).where(agent_tasks.c.id == task_id)).scalar()

def update_job_iterations_and_cost(job_id: int):
    """
    Updates the orchestration_jobs table with cumulative metrics from all related agent_tasks.
    This should be called when a job completes.
    """
    try:
        metrics = get_job_cumulative_metrics(job_id)
        if not metrics:
            logger.warning(f"No metrics found for job {job_id}.")
            return
        
        with engine.connect() as conn:
            stmt = update(orchestration_jobs).where(orchestration_jobs.c.id == job_id).values(
                total_iterations=metrics["total_iterations"],
                total_prompt_tokens=metrics["total_prompt_tokens"],
                total_completion_tokens=metrics["total_completion_tokens"],
                total_latency_ms=metrics["total_latency_ms"],
                total_cost_usd=metrics["total_cost_usd"],
                total_cost_twd=metrics["total_cost_twd"],
                used_models=metrics["used_models"],
                environmental_impact=metrics["environmental_impact"],
                updated_at=datetime.now(TAIPEI_TZ).replace(tzinfo=None)
            )
            conn.execute(stmt)
            conn.commit()
            logger.info(f"Updated job {job_id} cumulative metrics (Cost: ${metrics['total_cost_usd']}).")
    except Exception as e:
        logger.error(f"Failed to update job {job_id} iterations and cost. Reason: {e}")


def save_reference_feedback(
    chunk_id: Union[int, str], 
    rating: int, 
    teacher_id: int,
    comment: Optional[str] = None, 
    error_types: Optional[List[str]] = None,
    question_id: Optional[int] = None
) -> bool:
    """Saves user feedback for a reference chunk."""
    try:
        # Resolve string IDs (e.g. "doc_123" -> 123)
        actual_chunk_id = chunk_id
        if isinstance(chunk_id, str):
            if chunk_id.startswith("doc_"):
                actual_chunk_id = int(chunk_id[4:])
            elif chunk_id.startswith("gen_"):
                actual_chunk_id = int(chunk_id[4:])
            else:
                # Fallbck: try converting directly if it's just a number string
                try:
                    actual_chunk_id = int(chunk_id)
                except ValueError:
                    logger.warning(f"Skipping feedback save for non-integer chunk_id: {chunk_id}")
                    return False

        with engine.connect() as conn:
            # Use raw SQL to avoid SQLAlchemy Table metadata issues with newly added columns
            query = text("""
                INSERT INTO reference_feedbacks 
                (chunk_id, rating, teacher_id, question_id, comment, error_types, created_at)
                VALUES 
                (:chunk_id, :rating, :teacher_id, :question_id, :comment, :error_types, :created_at)
            """)
            
            conn.execute(query, {
                "chunk_id": actual_chunk_id,
                "rating": rating,
                "teacher_id": teacher_id,
                "question_id": question_id,
                "comment": comment,
                "error_types": json.dumps(error_types) if error_types else None,
                "created_at": datetime.now(TAIPEI_TZ).replace(tzinfo=None)
            })
            conn.commit()
            logger.info(f"Saved feedback for chunk {actual_chunk_id} (original: {chunk_id}) by teacher {teacher_id} (QID: {question_id}).")
            return True
    except Exception as e:
        logger.error(f"Failed to save feedback for chunk {chunk_id}. Reason: {e}")
        return False

def calculate_llm_cost(model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
    """
    Calculates the estimated cost of an LLM call in USD.
    Prices per 1M tokens based on standard OpenAI pricing.
    """
    pricing = {
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4o-2024-05-13": {"input": 5.00, "output": 15.00},
        "gpt-4o-2024-08-06": {"input": 2.50, "output": 10.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-4o-mini-2024-07-18": {"input": 0.15, "output": 0.60},
        "gpt-4-turbo": {"input": 10.00, "output": 30.00},
        "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
        "text-embedding-3-small": {"input": 0.02, "output": 0.00},
        "text-embedding-3-large": {"input": 0.13, "output": 0.00},
        "o1-preview": {"input": 15.00, "output": 60.00},
        "o1-mini": {"input": 1.10, "output": 4.40},
    }
    
    # Default to gpt-4o-mini if model not found
    model_key = model_name
    if model_key not in pricing:
        # Check if it's a prefix
        found = False
        for k in pricing:
            if model_key.startswith(k):
                model_key = k
                found = True
                break
        if not found:
            model_key = "gpt-4o-mini"
    
    costs = pricing.get(model_key)
    
    input_cost = (prompt_tokens / 1_000_000.0) * costs["input"]
    output_cost = (completion_tokens / 1_000_000.0) * costs["output"]
    
    return float(input_cost + output_cost)

