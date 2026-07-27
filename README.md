# Cook.ai

**CooK Teaching** — 為教師（不限科目、年級）設計的 AI 助教系統，提供 AI 出題、教材總結、知識點（KP）抽取與學生學習分析。教師端與學生端共用同一套後端。

> 📌 **完整系統架構、設計決策、交接細節**，見實驗室**私有交接 repo** `NCU-AIKslab/CooK.ai-2026-handoff`：
> `teacher_side_research/developer_handbook.md`（架構手冊）、`future_work.md`（待辦與已知問題）。
> 本 README 聚焦「**如何啟動與部署**」。

## 技術棧

| 層級 | 技術 |
|------|------|
| 前端 | React + Vite + TypeScript |
| 後端 | Python + **FastAPI**（ASGI / uvicorn） |
| AI 編排 | LangGraph（Teacher / Student Agents） |
| 資料庫 | PostgreSQL + pgvector |
| LLM | OpenAI API |
| DB 遷移 | Alembic |

## 環境設定

1. 複製範本並填入實際值：
   ```bash
   cp .env.example .env
   ```
2. 各變數「去哪申請、注意事項」見交接 repo 的 `teacher_side_research/ENV_SETUP.md`。
3. 關鍵變數：`OPENAI_API_KEY`、`DATABASE_URL`（PostgreSQL + pgvector）、`JWT_SECRET_KEY`、`VITE_API_URL`。

> ⚠️ `.env` 含 secrets，**切勿提交至 git**（已列入 `.gitignore`）。

## 開發環境啟動（本機）

### 後端

```bash
# 在專案根目錄
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 啟動（開發用，--reload 改檔自動重啟）
uvicorn backend.api_server:app --host 0.0.0.0 --port 8000 --reload
```

後端：`http://localhost:8000`，互動式 API 文件：`http://localhost:8000/docs`。

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端：`http://localhost:5173`（預設打 `http://localhost:8000`，見 `frontend/src/config/api.ts`）。

> **Port 注意**：純本機開發後端用 `:8000`；Docker 部署用 `:8888`（見下）。前端 `VITE_API_URL` 要對應後端實際位址。

## 生產環境部署（Docker）

Production 部署在獨立機器，使用 Docker：

```bash
cp .env.example .env          # 填入 production 值；VITE_API_URL 指向對外網址/IP
docker compose up -d --build
```

- **Port**：後端容器內 port `8888`，host 端對外綁 `18888`（共用機上 8888 已被佔用，故改用 18888）。**目前走 HTTP**。
- **GPU**：使用 `nvidia` runtime（`deploy.resources.reservations.devices`）。Host 需事先安裝 NVIDIA Container Toolkit。
- **持久化目錄（Volume）**：`./backend/storage`（上傳檔案）、`./backend/lime_reports`（LIME 評估報告）。**新增會被 backend 寫入的目錄都要記得加 volume**，否則 `--build` 會清空。
- Dockerfile 啟動指令為 `uvicorn ... --workers 2`（**無** `--reload`）。
- **⚠️ Worker 與 DB 連線數**：每個 worker 各有一個 DB 連線池（`pool_size=10 + max_overflow=20 = 30`）。`2 workers = 上限 60 條`連線到 RDS。**加 worker 前先確認 RDS `max_connections` 足夠**（小型實例約 80–100），否則會 `too many connections`。細節見交接 repo `future_work.md` §3.1。
- **RDS 防火牆**：新機器的對外 IP 要加進 RDS 安全組才連得到資料庫。

### 接手部署 SOP（精簡流程）

> 前提：機器已裝好 Docker + NVIDIA Container Toolkit、`.env` 已填好、可連到 PostgreSQL。

```bash
git pull origin production              # 1. 拉最新程式碼
docker compose up -d --build            # 2. build + 啟動（首次約 5–10 分鐘）

# 3. 驗證部署成功
docker ps | grep cookai                 # 看到 Up = 容器活著
docker logs cookai --tail 30            # 看到 "Application startup complete" = 啟動成功
docker exec cookai nvidia-smi           # 看得到顯卡 = GPU 有進 container
curl -I http://localhost:18888          # 預期 HTTP/1.1 405（HEAD 不被支援是正常的）
```

**修改後怎麼套用**：

| 改了什麼 | 指令 |
|----------|------|
| `.env` | `docker compose restart` |
| `docker-compose.yml`（volume / port / env_file…） | `docker compose up -d` |
| 程式碼 / `Dockerfile` / `requirements.txt` | `docker compose up -d --build` |
| 看即時 log | `docker compose logs -f`（Ctrl+C 離開） |
| 進 container debug | `docker exec -it cookai bash` |
| 停掉服務 | `docker compose down` |

## 資料庫遷移（Alembic）

```bash
alembic upgrade head                          # 套用到最新版本（部署新環境必跑）
alembic revision --autogenerate -m "描述變更"  # 依 model 變更產生 migration
alembic downgrade -1                          # 回滾一步
```

> ⚠️ 在共用 / 正式資料庫上跑 migration 前**務必通知所有協作者**。schema 與 alembic 細節見交接 repo `shared/`。

---

## 後端任務日誌（`@log_task` 裝飾器）

為了確保後端 Agent 的所有任務執行過程都能被詳細記錄，使用 `@log_task` 裝飾器。它自動處理任務的建立、狀態更新、執行時間、LLM token 用量及成本等日誌記錄，極大地簡化了 Agent 節點的程式碼。

**裝飾器定義**：`backend/app/utils/db_logger.py`

**使用方式**：將 `@log_task` 應用於任何 LangGraph 節點函式：

```python
from backend.app.utils.db_logger import log_task

@log_task(
    agent_name="your_agent_name",
    task_description="A brief description of what this task does.",
    input_extractor=lambda state: {"key_input_1": state.get("value_1")}
)
def your_node_function(state: YourAgentState) -> dict:
    # ... 節點的核心業務邏輯 ...
    result = {"some_output_key": "some_value"}

    # 若節點內部有 LLM 呼叫，請回傳以下 metrics 以便記錄
    return {
        **result,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "estimated_cost_usd": estimated_cost_usd
    }
```

**自動處理**：在 `agent_tasks` 表建立任務（`in_progress`）→ 將 `task_id` 注入 state（供子圖作 `parent_task_id`）→ 成功標記 `completed` 並記錄 output、失敗（拋例外或回傳含 `"error"`）標記 `failed` → 記錄 `duration_ms` 與 LLM metrics。

## 文件載入器與支援格式（Document Loaders）

後端具備文件載入器，能從多種來源與格式提取文字與圖片，標準化為 `Document` 物件（含 `content` 文字與 `images` Base64 圖片）傳給多模態 LLM。

- **上傳文件**：`.txt` / `.pdf`（pypdf）/ `.docx`（python-docx）/ `.pptx`（python-pptx）/ 圖片（PIL + pytesseract OCR + Base64）。圖片一律 OCR 後整合進 `content`。
- **網站匯入**：`WebBaseLoader` 抓文字；另用 BeautifulSoup 抓 `<img>` 下載後 OCR + Base64。
- **Google Drive**：OAuth2（`google-api-python-client`）下載後，依類型交給對應本地 Loader 處理。

> OCR 中文需安裝 Tesseract 及 `chi_tra` 語言包；Google Drive 需 `credentials.json`。

## 生成內容儲存慣例（Generated Content Storage）

所有存入 `generated_contents.content`（JSONB）的最終產出都含一個 `type` 鍵，值與 `content_type` 欄位一致，是前端判斷如何渲染的依據：

```jsonc
// 聊天訊息
{ "type": "message", "content": "您好！我是一位 AI 教學助理..." }

// 總結報告
{ "type": "summary", "main_title": "...", "sections": [ { "title": "...", "content_list": ["..."] } ] }

// 考卷題目
{ "type": "exam_questions", "questions": [ { "question_number": 1, "question_text": "...", "options": {}, "correct_answer": "...", "source": {} } ] }
```