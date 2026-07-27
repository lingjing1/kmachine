"""
Enhanced API Performance Diagnostic Middleware
Add this to backend/api_server.py to identify blocking operations
"""
import time
import asyncio
import logging
from contextvars import ContextVar
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("api_diagnostics")
logger.setLevel(logging.INFO)

# Context variable to store timing checkpoints
timing_checkpoints: ContextVar[list] = ContextVar('timing_checkpoints', default=[])

class PerformanceDiagnosticMiddleware(BaseHTTPMiddleware):
    """
    Middleware to diagnose API performance issues
    Logs detailed timing for slow requests (>1s)
    """
    
    async def dispatch(self, request: Request, call_next):
        # Reset timing checkpoints for this request
        checkpoints = []
        timing_checkpoints.set(checkpoints)
        
        start_time = time.time()
        
        # Add checkpoint for request start
        checkpoints.append(("request_start", start_time))
        
        # Execute the request
        response = await call_next(request)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Add checkpoint for request end
        checkpoints.append(("request_end", end_time))
        
        # Log detailed timing for slow requests
        if total_time > 1.0:
            self._log_slow_request(request, total_time, checkpoints)
        
        return response
    
    def _log_slow_request(self, request: Request, total_time: float, checkpoints: list):
        """Log detailed breakdown of slow requests"""
        logger.warning(f"🐌 SLOW REQUEST DETECTED: {request.method} {request.url.path} - {total_time:.4f}s")
        
        if len(checkpoints) > 2:
            logger.warning(f"   Timing breakdown:")
            for i in range(len(checkpoints) - 1):
                name1, time1 = checkpoints[i]
                name2, time2 = checkpoints[i + 1]
                duration = time2 - time1
                logger.warning(f"      {name1} → {name2}: {duration:.4f}s")
        else:
            logger.warning(f"   No timing checkpoints recorded. Likely blocking operation.")


# Helper function to add timing checkpoints within endpoints
def add_timing_checkpoint(name: str):
    """
    Add a timing checkpoint within an endpoint
    
    Usage:
        from backend.app.monitoring import add_timing_checkpoint
        
        @router.get("/api/slow-endpoint")
        async def slow_endpoint():
            add_timing_checkpoint("after_validation")
            result = await db.query(...)
            add_timing_checkpoint("after_db_query")
            processed = process_data(result)
            add_timing_checkpoint("after_processing")
            return processed
    """
    try:
        checkpoints = timing_checkpoints.get()
        checkpoints.append((name, time.time()))
    except LookupError:
        # Context variable not set (not within middleware)
        pass


# Example: How to instrument a slow endpoint
"""
from backend.app.monitoring import add_timing_checkpoint

@router.get("/api/teacher/courses/{course_id}/enrollment-code")
async def get_course_enrollment_code(course_id: int):
    add_timing_checkpoint("start_handler")
    
    with engine.connect() as conn:
        add_timing_checkpoint("db_connection_acquired")
        
        query = text("SELECT ...")
        result = conn.execute(query, {"course_id": course_id}).fetchone()
        add_timing_checkpoint("db_query_complete")
        
        # ... validation logic ...
        add_timing_checkpoint("validation_complete")
        
    return response
"""

# Usage in api_server.py:
"""
from backend.app.monitoring import PerformanceDiagnosticMiddleware

app = FastAPI()
app.add_middleware(PerformanceDiagnosticMiddleware)
"""
