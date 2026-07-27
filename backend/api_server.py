from fastapi import FastAPI, Request
import logging
# Force reload trigger
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# Import routers
# from backend.app.routers import debugging_problems  # Temporarily disabled - requires OJ_DATABASE_URL env var
from backend.app.routers import auth_router
from backend.app.core.prompt_manager import prompt_manager

# Force reload prompts to ensure latest YAML changes are picked up
prompt_manager.reload()
from backend.app.routers import teacher_agent_router
from backend.app.routers import teacher_data_router
from backend.app.routers import teacher_testing_router
from backend.app.routers import teacher_course_router
from backend.app.routers import grading_router
from backend.app.routers import student_chatbot_router  # 新增學生 chatbot router

# --- FastAPI App ---

# Create the FastAPI app
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import json

app = FastAPI(
    title="Cook.ai API Server",
    description="API for ingesting documents and generating educational materials.",
)

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    try:
        body = await request.body()
        error_msg = str(exc.errors())
        with open("error.log", "a") as f:
            f.write(f"Validation error for {request.url}\n")
            f.write(f"Errors: {error_msg}\n")
            f.write(f"Body: {body.decode()}\n")
    except Exception:
        pass
    
    safe_errors = [{"loc": err.get("loc"), "msg": err.get("msg"), "type": err.get("type")} for err in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": safe_errors})

# --- Add CORS Middleware ---
origins = [
    "http://localhost:5173", # Lab IP
    "http://127.0.0.1:5173", # Lab IP
    "http://localhost:3001", # Lab IP
    "http://127.0.0.1:3001", # Lab IP
    "http://140.115.54.161:8888", # Prod API
    "http://140.115.54.162:3001", # Current Dev Frontend
    "http://140.115.54.162:3002", # Current Dev Frontend Alternative
    "https://coolknowledge.ai", # 正式環境網域
    "https://www.coolknowledge.ai", # 包含 www 的版本
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"^https://.*\.coolknowledge\.ai$", # Allow all subdomains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    import time
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    # Filter out polling endpoints (jobs status checks)
    if "/api/v1/jobs/" not in request.url.path:
        # Log slow requests (>1s) as warnings, others as debug
        logger = logging.getLogger("uvicorn.error")
        msg = f"[API] {request.method} {request.url.path} - {process_time:.4f}s"
        if process_time > 1.0:
            logger.warning(msg)
        else:
            logger.debug(msg)
    # Log headers for debugging CORS
    if request.method == "OPTIONS":
        logger = logging.getLogger("uvicorn.error")
        logger.info(f"[CORS Debug] Response Headers: {dict(response.headers)}")

    return response

# --- Mount Static Files ---
# Mount LIME reports directory for frontend access
import os
from backend.app.config.settings import settings

lime_reports_dir = os.path.join(os.path.dirname(__file__), "lime_reports")
if os.path.exists(lime_reports_dir):
    app.mount("/lime_reports", StaticFiles(directory=lime_reports_dir), name="lime_reports")

# Mount uploads directory for images and downloaded materials
if os.path.exists(settings.upload_dir):
    app.mount("/uploads", StaticFiles(directory=str(settings.upload_dir)), name="uploads")

# --- Frontend 靜態檔偵測（合併 image）---
# 有 frontend/dist 才啟用 serve 前端；本機開發無 dist → 維持原本行為（/ 轉 /docs）。
frontend_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
_frontend_index = os.path.join(frontend_dist, "index.html")
_serve_frontend = os.path.isfile(_frontend_index)

# --- Root, Health Check ---

@app.get("/", include_in_schema=False)
def read_root():
    """
    合併部署（有 dist）時回傳前端首頁；純後端時轉址到 API 文件 /docs。
    """
    if _serve_frontend:
        return FileResponse(_frontend_index)
    return RedirectResponse(url="/docs")

@app.get("/health", tags=["System"])
def health_check():
    """
    A simple health check endpoint that returns the server status.
    """
    return {"status": "ok"}

# --- Register Routers ---

# Teacher-side routers (教師端)
from backend.app.routers import teacher_dashboard_router
app.include_router(teacher_dashboard_router.router)
app.include_router(teacher_agent_router.router)
app.include_router(teacher_data_router.router)
app.include_router(teacher_course_router.router)

from backend.app.routers import teacher_rating_router
app.include_router(teacher_rating_router.router)

from backend.app.routers import teacher_grades_router
app.include_router(teacher_grades_router.router)

# Teacher enrollment code (課程代碼)
from backend.app.routers import teacher_enrollment_router
app.include_router(teacher_enrollment_router.router)

# Teacher experiment evaluations (實驗評估系統)
from backend.app.routers import teacher_experiment_router
app.include_router(teacher_experiment_router.router)

# Teacher Kappa evaluation center (教師 Kappa 評估中心 - course 62 / finetune dataset)
from backend.app.routers import teacher_kappa_eval_router
app.include_router(teacher_kappa_eval_router.router)

app.include_router(auth_router.router)

# Admin management (管理員後台)
from backend.app.routers import admin_router
app.include_router(admin_router.router)

# Grading system (成績系統)
app.include_router(grading_router.router)

# Attachment management (附件管理)
from backend.app.routers import attachment_router, attachment_viewer_router
app.include_router(attachment_router.router)
app.include_router(attachment_viewer_router.router)

# Document serving for students (學生文檔訪問)
from backend.app.routers import document_router
app.include_router(document_router.router)


# Student chatbot (學生對話機器人)
from backend.app.routers import student_dashboard_router
app.include_router(student_dashboard_router.router)
app.include_router(student_chatbot_router.router)

# Student preview flow (學生課前預習)
from backend.app.routers import student_preview_router
app.include_router(student_preview_router.router)

# Student submission (作業/考試提交)
from backend.app.routers import student_submission_router
app.include_router(student_submission_router.router)

# File submissions (檔案繳交)
from backend.app.routers import file_submission_router
app.include_router(file_submission_router.router)

# Student mastery (學生精熟度評估)
from backend.app.routers import student_mastery_router
app.include_router(student_mastery_router.router)

# Student review flow (學生課後複習)
from backend.app.routers import student_review_router
app.include_router(student_review_router.router)

# Student course related (學生課程/公告)
from backend.app.routers import student_course_router
app.include_router(student_course_router.router)

# Student material ratings (學生教材評分)
from backend.app.routers import material_rating_router
app.include_router(material_rating_router.router)

# Student reading logs (學生閱讀軌跡)
from backend.app.routers import student_reading_router, student_session_router
app.include_router(student_reading_router.router)
app.include_router(student_session_router.router)

# Student Grades (學生個人成績)
from backend.app.routers import student_grades_router
app.include_router(student_grades_router.router)

# Question Bank (題庫管理)
from backend.app.routers import question_bank_router
app.include_router(question_bank_router.router)

# Knowledge Point Extraction (知識點提取)
from backend.app.routers import kp_router
app.include_router(kp_router.router)

# Feedback Center (意見回饋中心)
from backend.app.routers import feedback_router
app.include_router(feedback_router.router)

# Teacher Action Logs (教師生成頁面動作日誌)
from backend.app.routers import generator_log_router
app.include_router(generator_log_router.router)

# ... (previous code)

# --- Logging Configuration ---

class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Filter out GET /api/v1/jobs/ requests (polling)
        return record.getMessage().find("GET /api/v1/jobs/") == -1

# Filter uvicorn access logs
logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

# --- Database Pool Monitoring ---
@app.on_event("startup")
async def monitor_pool():
    import threading
    import time
    from backend.app.db import engine
    
    logger = logging.getLogger("uvicorn.error") # Use uvicorn logger for visibility

    def log_pool_status():
        try:
            pool = engine.pool
            # Check internal pool status if available
            # .size() is pool_size, .checkedout() is current busy connections
            msg = f"[DB Pool] Size: {pool.size()}, Checked out: {pool.checkedout()}, Overflow: {pool.overflow()}"
            logger.info(msg)
        except Exception as e:
            logger.error(f"[DB Pool] Error checking pool: {e}")

    def periodic_log():
        while True:
            log_pool_status()
            time.sleep(300) # Log every 5 minutes (reduced from 60s)

    threading.Thread(target=periodic_log, daemon=True).start()

# To run this server:
# 1. Make sure you are in the root directory of the project (Cook.ai).
# 2. Run the command: uvicorn backend.api_server:app --reload --port 8000


# --- SPA 靜態檔服務（合併 image）---
# 必須在所有 /api 路由「之後」註冊，才不會誤蓋掉 API（catch-all 放最後）。
# 有前端 dist 才掛載；本機開發無 dist → 不註冊，/ 與 API 行為完全不變。
if _serve_frontend:
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        # 命中既有靜態檔（JS/CSS/favicon 等）→ 回該檔；否則回 index.html 交給前端 router
        candidate = os.path.join(frontend_dist, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(_frontend_index)
