# ============================================================
# Cook.ai 合併部署 image（前端 + 後端，GPU）
#
# Build:  docker build -t cookai:latest .
# Run:    docker run --gpus all -p 127.0.0.1:8888:8888 \
#               --env-file .env_4090 --name cookai cookai:latest
#
# 架構：後端 FastAPI 同時 serve 前端靜態檔 + API（同 origin，免 CORS）。
# 前端 build 時 VITE_API_URL 留空 → 走相對 /api，換網域免重 build。
# ============================================================

# ---- Stage 1: build 前端 ----
FROM node:20-slim AS frontend-builder
WORKDIR /app

# vite.config.ts 的 envDir 設為上一層 '../'，所以在 /app 放 .env，build 時 /app/frontend 的 vite 會讀到。
# VITE_API_URL 預設留空 → 相對 /api（同 origin，換網域免重 build）
ARG VITE_API_URL=""
RUN echo "VITE_API_URL=${VITE_API_URL}" > /app/.env

# 先裝相依（利用 layer cache：lock 檔沒變就不重裝）
COPY frontend/package.json frontend/package-lock.json ./frontend/
WORKDIR /app/frontend
RUN npm ci

# 複製前端原始碼並 build
COPY frontend/ ./
RUN npm run build
# 產出：/app/frontend/dist


# ---- Stage 2: 後端 + serve 前端 ----
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GIT_PYTHON_REFRESH=quiet \
    PYTHONPATH=/app
WORKDIR /app

# 系統相依（編譯部分 python 套件 + libpq）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev git \
    && rm -rf /var/lib/apt/lists/*

# 先裝 python 相依（含 GPU torch + nvidia-cuda）— 放前面利用 layer cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製後端程式碼 + BERT 模型（391MB，.dockerignore 已排除 venv/node_modules/dist）
COPY . .

# 複製前端 build 產物到 backend 偵測的路徑（api_server.py: ../frontend/dist）
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# storage 需可寫
RUN mkdir -p /app/backend/storage && chmod -R 777 /app/backend/storage

EXPOSE 8888

# 生產：不加 --reload（避免檔案變動殺掉背景任務）。
# --workers 2：每個 worker 各自載一份 BERT 模型到 GPU；GPU 記憶體不足可降為 1。
CMD ["uvicorn", "backend.api_server:app", "--host", "0.0.0.0", "--port", "8888", "--workers", "2"]
