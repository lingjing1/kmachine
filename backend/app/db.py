from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.app.config.settings import settings

DATABASE_URL = settings.database_url

# 🔥 唯一的 Engine 實例 - 所有模組都應該從這裡 import
engine = create_engine(
    DATABASE_URL,
    pool_size=10,          # 連線池大小
    max_overflow=20,       # 最多額外連線數
    pool_pre_ping=True,    # 防止 DBeaver 等客戶端斷線導致的錯誤
    pool_recycle=3600,     # 1小時後回收連線
    echo=False             # 生產環境設為 False
)

metadata = MetaData()
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# FastAPI Dependency
def get_db():
    """
    FastAPI 用的 DB Session Dependency
    確保每個請求結束後都會關閉 Session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
