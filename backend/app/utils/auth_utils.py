"""
JWT Authentication Utilities

提供 JWT token 的生成、驗證和使用者身份提取功能
"""
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from backend.app.config.settings import settings

# HTTP Bearer 認證 scheme
security = HTTPBearer()


def create_access_token(user_id: int, email: str, role: str) -> str:
    """
    生成 JWT access token
    
    Args:
        user_id: 使用者 ID
        email: 使用者 email
        role: 使用者角色 (teacher, student, TA)
    
    Returns:
        JWT token 字串
    """
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    to_encode = {
        "user_id": user_id,
        "email": email,
        "role": role,
        "exp": expire
    }
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt


def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> dict:
    """
    驗證 JWT token 並返回 payload
    
    Args:
        credentials: HTTP Bearer token credentials
    
    Returns:
        Token payload (包含 user_id, email, role, exp)
    
    Raises:
        HTTPException: Token 無效或過期時拋出 401 錯誤
    """
    try:
        token = credentials.credentials
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user_id(credentials: HTTPAuthorizationCredentials = Security(security)) -> int:
    """
    從 JWT token 取得當前使用者 ID
    
    用於 FastAPI dependency injection，自動從 Authorization header 提取 user_id。
    
    Args:
        credentials: HTTP Bearer token credentials
    
    Returns:
        使用者 ID
    """
    payload = verify_token(credentials)
    user_id = payload.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return user_id


def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)) -> dict:
    """
    從 JWT token 取得完整的當前使用者資訊
    
    Args:
        credentials: HTTP Bearer token credentials
    
    Returns:
        使用者資訊字典 (包含 user_id, email, role)
    
    Raises:
        HTTPException: Token 無效時拋出 401 錯誤
    
    Example:
        @router.get("/profile")
        async def get_profile(user: dict = Depends(get_current_user)):
            return {
                "user_id": user["user_id"],
                "email": user["email"],
                "role": user["role"]
            }
    """
    return verify_token(credentials)


def require_admin(credentials: HTTPAuthorizationCredentials = Security(security)) -> dict:
    """
    驗證當前使用者是否具有 admin 角色

    用於 FastAPI dependency injection，保護管理員專用端點。
    登入時若 role 為 'admin'，JWT payload 中的 role 欄位即為 'admin'。

    Args:
        credentials: HTTP Bearer token credentials

    Returns:
        Token payload (包含 user_id, email, role)

    Raises:
        HTTPException 401: Token 無效或過期
        HTTPException 403: 使用者角色不是 admin
    """
    payload = verify_token(credentials)
    if payload.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="此操作需要管理員權限",
        )
    return payload


def require_teacher(credentials: HTTPAuthorizationCredentials = Security(security)) -> dict:
    """
    驗證當前使用者是否具有 teacher 角色

    Args:
        credentials: HTTP Bearer token credentials

    Returns:
        Token payload (包含 user_id, email, role)

    Raises:
        HTTPException 401: Token 無效或過期
        HTTPException 403: 使用者角色不是 teacher
    """
    payload = verify_token(credentials)
    if payload.get("role") not in ["teacher", "admin"]:
        raise HTTPException(
            status_code=403,
            detail="此操作需要教師或管理員權限",
        )
    return payload


def make_require_teacher_or_course_ta(course_id: int):
    """
    工廠函數：建立一個 FastAPI dependency，驗證使用者是該課程的老師或助教。

    用法:
        @router.get("/{course_id}/something")
        async def endpoint(
            course_id: int,
            user=Depends(make_require_teacher_or_course_ta(course_id))
        ):
            ...

    Note: 由於 FastAPI 的 path parameter 與 Depends 的整合限制，
    建議在 endpoint 內直接呼叫 check_teacher_or_course_ta() 進行驗證。
    """
    from fastapi import Depends
    from sqlalchemy import text as sa_text
    from backend.app.utils.db_logger import engine

    async def dependency(credentials: HTTPAuthorizationCredentials = Security(security)) -> dict:
        payload = verify_token(credentials)
        user_id = payload.get("user_id")
        role = payload.get("role")

        if role == "teacher":
            # Teacher: verify they own this course
            with engine.connect() as conn:
                row = conn.execute(
                    sa_text("SELECT id FROM courses WHERE id = :cid AND teacher_id = :uid"),
                    {"cid": course_id, "uid": user_id}
                ).fetchone()
                if not row:
                    raise HTTPException(status_code=403, detail="您不是此課程的授課教師")
        else:
            # Check if user is a TA for this course
            with engine.connect() as conn:
                row = conn.execute(
                    sa_text(
                        "SELECT 1 FROM enrollments WHERE user_id = :uid AND course_id = :cid AND role = 'ta'"
                    ),
                    {"uid": user_id, "cid": course_id}
                ).fetchone()
                if not row:
                    raise HTTPException(status_code=403, detail="此操作需要教師或助教權限")

        return payload

    return dependency


def check_teacher_or_course_ta(user_id: int, course_id: int, conn) -> bool:
    """
    同步版本：檢查 user 是否為該課程的老師或助教。
    在已有 DB connection 的情況下直接呼叫，避免重複開關連線。

    Args:
        user_id: 使用者 ID
        course_id: 課程 ID
        conn: SQLAlchemy connection

    Returns:
        True 若有權限，否則 raise HTTPException 403
    """
    from sqlalchemy import text as sa_text

    role = conn.execute(
        sa_text("SELECT r.name FROM users u JOIN roles r ON u.role_id = r.id WHERE u.id = :uid"),
        {"uid": user_id}
    ).scalar()

    if role == "admin":
        return True

    # Check if teacher of this course
    is_teacher = conn.execute(
        sa_text("SELECT id FROM courses WHERE id = :cid AND teacher_id = :uid"),
        {"cid": course_id, "uid": user_id}
    ).fetchone()

    if is_teacher:
        return True

    # Check if TA for this course
    is_ta = conn.execute(
        sa_text(
            "SELECT 1 FROM enrollments WHERE user_id = :uid AND course_id = :cid AND role = 'ta'"
        ),
        {"uid": user_id, "cid": course_id}
    ).fetchone()

    if is_ta:
        return True

    raise HTTPException(status_code=403, detail="此操作需要教師或助教權限")

