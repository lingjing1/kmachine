from typing import List, Dict, Any, TypedDict, Optional, Literal

class SummarizationState(TypedDict):
    """
    Represents the state for the summarization skill.
    """
    # Basic inputs
    job_id: str
    query: str
    source_ids: List[int]
    generated_source_ids: Optional[List[int]]  # Added for generated content sources
    selected_kp_names: Optional[List[str]]  # Selected KP names for RAG optimization
    material_type: Optional[Literal["preview", "review"]]  # Material type: preview or review
    length: Optional[Literal["concise", "standard", "detailed"]]  # Summary length mode
    unit_name: Optional[str]  # Topic context for summarization
    unit_id: Optional[int]  # Added for unit-context retrieval
    ablation_group: Optional[str] # Experimental group for ablation study

    
    # RAG stage
    retrieved_page_content: List[Dict[str, Any]]
    retrieved_text_chunks: List[Dict[str, Any]]  # For citation attribution
    
    # Generation stage
    final_generated_content: Optional[Dict[str, Any]]
    error: Optional[str]
    
    # Logging and graph flow
    parent_task_id: Optional[int]
    current_task_id: Optional[int]
    
    # Token tracking (consistent with exam generator)
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    estimated_cost_usd: Optional[float]
    model_name: Optional[str]
    critic_feedback: Optional[List[Dict[str, Any]]] # Feedback from critics for refinement
    iteration_count: Optional[int] # Current iteration number
