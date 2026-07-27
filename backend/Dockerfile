# Use the official Python 3.10 slim image as a base
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV GIT_PYTHON_REFRESH=quiet

# Create a working directory in the container
WORKDIR /app

# Install system dependencies (including gcc for building some python packages if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy the dependency list from the build context (root)
COPY requirements.txt .

# Install all dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all your code
COPY . .

# Create storage directory and ensure it's writeable
RUN mkdir -p /app/backend/storage && chmod -R 777 /app/backend/storage

# Expose port 8888
EXPOSE 8888

# Command to run when the container starts.
# 生產環境:移除 --reload(會在檔案變動時重啟,殺掉進行中的背景生成任務)。
# --workers 2:開 2 個工作進程提升並發容量。
#   注意連線數:每個 worker 各自有一個 DB 連線池(pool_size=10 + max_overflow=20 = 30)。
#   2 workers 上限 = 60 條連線到 RDS;確認 RDS max_connections 足夠後可再往上調。
CMD ["uvicorn", "backend.api_server:app", "--host", "0.0.0.0", "--port", "8888", "--workers", "2"]
