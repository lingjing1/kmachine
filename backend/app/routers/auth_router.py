"""
Authentication router: 處理使用者註冊、登入等功能
"""
from fastapi import APIRouter, HTTPException, File, UploadFile, Form, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
import os
import uuid
from pathlib import Path
from passlib.context import CryptContext
from sqlalchemy import Table, select, insert, delete, text
from datetime import datetime, timedelta, timezone
from backend.app.utils.time_utils import get_now_taipei
from backend.app.utils.db_logger import engine, metadata
from backend.app.constants.departments import ALL_DEPARTMENTS
from backend.app.services.email_service import generate_verification_code, send_verification_email, send_teacher_verification_email
from backend.app.utils.concurrency import run_in_db_pool
from backend.app.utils.auth_utils import create_access_token  # ✅ 新增

# 建立 Router
router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# 密碼加密設定 - 使用 Argon2（更安全，無長度限制）
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# HTTP Bearer 認證 scheme（用於 refresh-token）
security = HTTPBearer()

# 反射資料表
try:
    users_table = Table('users', metadata, autoload_with=engine)
    roles_table = Table('roles', metadata, autoload_with=engine)
    user_authentications_table = Table('user_authentications', metadata, autoload_with=engine)
    student_profiles_table = Table('student_profiles', metadata, autoload_with=engine)
    teacher_profiles_table = Table('teacher_profiles', metadata, autoload_with=engine)
    email_verifications_table = Table('email_verifications', metadata, autoload_with=engine)
except Exception as e:
    print(f"Error reflecting authentication tables: {e}")

# ==================== Pydantic Schemas ====================

class RegisterRequest(BaseModel):
    """註冊請求"""
    email: EmailStr = Field(..., description="使用者 Email")
    password: str = Field(..., min_length=6, description="使用者密碼 (至少 6 個字元)")
    full_name: str = Field(..., min_length=1, max_length=100, description="使用者姓名")
    student_id: str = Field(..., min_length=1, max_length=100, description="學號 (必填)")
    role: str = Field("student", description="使用者角色: teacher, student, TA (預設: student)")
    major: str = Field(..., max_length=100, description="科系 (必填)")
    
    @field_validator('major')
    @classmethod
    def validate_major(cls, v: str) -> str:
        """檢查科系是否有效（允許自訂科系名稱）"""
        v = v.strip()
        if not v:
            raise ValueError('科系不能為空')
        return v


class RegisterResponse(BaseModel):
    """註冊成功回應"""
    user_id: int
    email: str
    full_name: str
    role: str
    message: str = "註冊成功"


class SendVerificationCodeRequest(BaseModel):
    """發送驗證碼請求"""
    email: EmailStr = Field(..., description="要驗證的 Email")
    user_type: str = Field("student", description="使用者類型: student, teacher（決定郵件內容）")


class SendVerificationCodeResponse(BaseModel):
    """發送驗證碼回應"""
    message: str
    expires_in_minutes: int = 3


class VerifyCodeRequest(BaseModel):
    """驗證驗證碼請求"""
    email: EmailStr = Field(..., description="Email")
    code: str = Field(..., min_length=6, max_length=6, description="6 位數驗證碼")


class VerifyCodeResponse(BaseModel):
    """驗證驗證碼回應"""
    verified: bool
    message: str


class LoginRequest(BaseModel):
    """登入請求"""
    email: EmailStr = Field(..., description="使用者 Email")
    password: str = Field(..., min_length=6, description="使用者密碼")


class LoginResponse(BaseModel):
    """登入成功回應"""
    user_id: int
    email: str
    full_name: str
    role: str
    access_token: str  # ✅ 新增 JWT token
    token_type: str = "bearer"  # ✅ 新增 token 類型
    message: str = "登入成功"


# ==================== Helper Functions ====================

def hash_password(password: str) -> str:
    """將明文密碼加密"""
    return pwd_context.hash(password)


def _sync_get_role_id(role_name: str) -> Optional[int]:
    """根據角色名稱取得 role_id"""
    with engine.connect() as conn:
        query = select(roles_table.c.id).where(roles_table.c.name == role_name)
        result = conn.execute(query).fetchone()
        return result[0] if result else None

async def get_role_id(role_name: str) -> Optional[int]:
    """根據角色名稱取得 role_id (Async)"""
    return await run_in_db_pool(_sync_get_role_id, role_name)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """驗證密碼是否正確"""
    return pwd_context.verify(plain_password, hashed_password)


# ==================== API Endpoints ====================

@router.post("/send-verification-code", response_model=SendVerificationCodeResponse)
async def send_verification_code(request: SendVerificationCodeRequest):
    """
    發送驗證碼到指定 Email
    
    流程：
    1. 生成 6 位數驗證碼
    2. 儲存到資料庫 (有效期 5 分鐘)
    3. 發送郵件
    """
    def _sync_send_code(email):
        with engine.connect() as conn:
            # 生成驗證碼
            code = generate_verification_code()
            expires_at = get_now_taipei() + timedelta(minutes=3)
            
            # 刪除該 Email 的舊驗證碼
            delete_stmt = delete(email_verifications_table).where(
                email_verifications_table.c.email == email
            )
            conn.execute(delete_stmt)
            
            # 插入新驗證碼
            insert_stmt = insert(email_verifications_table).values(
                email=email,
                code=code,
                expires_at=expires_at,
                created_at=get_now_taipei(),
                is_used=False
            )
            conn.execute(insert_stmt)
            conn.commit()
            return code

    code = await run_in_db_pool(_sync_send_code, request.email)

    if request.user_type == "teacher":
        success = await run_in_db_pool(send_teacher_verification_email, request.email, code)
    else:
        success = await run_in_db_pool(send_verification_email, request.email, code)
    
    if not success:
        raise HTTPException(status_code=500, detail="發送驗證碼失敗，請稍後再試")
    
    return SendVerificationCodeResponse(
        message="驗證碼已發送至您的信箱",
        expires_in_minutes=3
    )


@router.post("/verify-code", response_model=VerifyCodeResponse)
async def verify_code(request: VerifyCodeRequest):
    """
    驗證驗證碼是否正確
    
    流程：
    1. 檢查驗證碼是否存在且未過期
    2. 檢查是否已使用
    3. 標記為已使用
    """
    def _sync_verify_code(email, code):
        with engine.connect() as conn:
            # 查詢驗證碼
            query = select(email_verifications_table).where(
                (email_verifications_table.c.email == email) &
                (email_verifications_table.c.code == code) &
                (email_verifications_table.c.is_used == False) &
                (email_verifications_table.c.expires_at > get_now_taipei())
            )
            result = conn.execute(query).fetchone()
            
            if not result:
                return False, "驗證碼錯誤或已過期"
            
            # 標記為已使用
            from sqlalchemy import update
            update_stmt = update(email_verifications_table).where(
                (email_verifications_table.c.email == email) &
                (email_verifications_table.c.code == code)
            ).values(is_used=True)
            conn.execute(update_stmt)
            conn.commit()
            
            return True, "驗證成功"

    verified, message = await run_in_db_pool(_sync_verify_code, request.email, request.code)
    
    return VerifyCodeResponse(
        verified=verified,
        message=message
    )


@router.post("/register", response_model=RegisterResponse)
async def register_user(request: RegisterRequest):
    """
    使用者註冊端點
    
    流程：
    1. 檢查 Email 和 Full Name 配對是否已存在（防止重複註冊）
    2. 驗證角色是否有效
    3. 建立 users 記錄
    4. 建立 user_authentications 記錄 (加密密碼)
    5. 建立 student_profiles 記錄 (student_id 和 major 都是必填)
    """
    
    # 2. 取得 role_id (Async)
    role_id = await get_role_id(request.role)
    if not role_id:
        raise HTTPException(status_code=400, detail=f"無效的角色: {request.role}")
            
    # Hash password outside of DB lock to save time
    hashed_password = hash_password(request.password)

    def _sync_register_user(req, rid, h_pass):
        from sqlalchemy.exc import IntegrityError
        with engine.connect() as conn:
            # 1. 檢查 Email 和 Full Name 配對是否已存在（防止重複註冊）
            existing_user = conn.execute(
                select(users_table).where(
                    (users_table.c.email == req.email) & 
                    (users_table.c.full_name == req.full_name)
                )
            ).fetchone()
            
            if existing_user:
                return None, "此帳號已被註冊（Email 和姓名配對已存在）"
            
            user_insert = insert(users_table).values(
                email=req.email,
                full_name=req.full_name,
                role_id=rid,
                status='active',  # 學生註冊立即啟用
                created_time=get_now_taipei()
            )
            try:
                result = conn.execute(user_insert)
            except IntegrityError:
                conn.rollback()
                return None, "此 Email 已被其他帳號使用，請確認姓名是否填寫正確"
            user_id = result.inserted_primary_key[0]
            
            # 4. 建立 user_authentications 記錄
            auth_insert = insert(user_authentications_table).values(
                user_id=user_id,
                provider="local",
                password=h_pass
            )
            conn.execute(auth_insert)
            
            # 5. 建立 student_profiles 記錄（student_id 現在是必填）
            # 檢查學號是否重複
            existing_student = conn.execute(
                select(student_profiles_table).where(
                    student_profiles_table.c.student_id == req.student_id
                )
            ).fetchone()
            
            if existing_student:
                conn.rollback()
                return None, "此學號已被註冊"
            
            profile_insert = insert(student_profiles_table).values(
                user_id=user_id,
                student_id=req.student_id,
                major=req.major
            )
            conn.execute(profile_insert)
            
            # 提交事務
            conn.commit()
            return user_id, None

    user_id, error = await run_in_db_pool(_sync_register_user, request, role_id, hashed_password)
    
    if error:
        raise HTTPException(status_code=400, detail=error)
    
    return RegisterResponse(
        user_id=user_id,
        email=request.email,
        full_name=request.full_name,
        role=request.role
    )


# ==================== 教師註冊端點 ====================

@router.post("/register/teacher")
async def register_teacher(
    email: str = Form(...),
    password: str = Form(min_length=6),
    full_name: str = Form(...),
    institution: str = Form(...),
    proof_document: UploadFile = File(None)
):
    """
    教師註冊端點
    
    流程：
    1. 檢查 Email 是否已註冊
    2. 建立 users 記錄 (status='pending')
    3. 建立 user_authentications 記錄
    4. 儲存證明文件（如果有）
    5. 建立 teacher_profiles 記錄
    """
    
    # 2. 取得 teacher role_id
    role_id = await get_role_id("teacher")
    if not role_id:
        raise HTTPException(status_code=400, detail="無效的角色")
        
    hashed_password = hash_password(password)
    
    # Process proof doc if needs async read
    proof_content = None
    proof_filename = None
    if proof_document and proof_document.filename:
        proof_content = await proof_document.read()
        proof_filename = proof_document.filename

    def _sync_register_teacher(email_val, name_val, rid, h_pass, inst_val, proof_fname, proof_cont):
        with engine.connect() as conn:
            # 1. 檢查 Email 是否已註冊
            existing_user = conn.execute(
                select(users_table).where(users_table.c.email == email_val)
            ).fetchone()
            
            if existing_user:
                return None, "此 Email 已被註冊"
            
            user_insert = insert(users_table).values(
                email=email_val,
                full_name=name_val,
                role_id=rid,
                status='pending',  # 教師需要審核
                created_time=get_now_taipei()
            )
            result = conn.execute(user_insert)
            user_id = result.inserted_primary_key[0]
            
            # 4. 建立 user_authentications 記錄
            auth_insert = insert(user_authentications_table).values(
                user_id=user_id,
                provider="local",
                password=h_pass
            )
            conn.execute(auth_insert)
            
            # 5. 儲存證明文件（如果有）
            proof_url = None
            if proof_fname and proof_cont:
                # 建立上傳目錄
                upload_dir = Path("uploads/proof_documents")
                upload_dir.mkdir(parents=True, exist_ok=True)
                
                # 生成唯一檔名
                file_ext = Path(proof_fname).suffix
                file_name = f"user_{user_id}_{uuid.uuid4()}{file_ext}"
                file_path = upload_dir / file_name
                
                # 儲存檔案
                with open(file_path, "wb") as f:
                    f.write(proof_cont)
                
                proof_url = str(file_path)
            
            # 6. 建立 teacher_profiles 記錄
            profile_insert = insert(teacher_profiles_table).values(
                user_id=user_id,
                institution=inst_val,
                proof_document_url=proof_url,
                created_at=get_now_taipei(),
                updated_at=get_now_taipei()
            )
            conn.execute(profile_insert)
            
            # 提交事務
            conn.commit()
            return user_id, None

    user_id, error = await run_in_db_pool(
        _sync_register_teacher, 
        email, full_name, role_id, hashed_password, institution, proof_filename, proof_content
    )
    
    if error:
        raise HTTPException(status_code=400, detail=error)
    
    return {
        "user_id": user_id,
        "email": email,
        "full_name": full_name,
        "role": "teacher",
        "status": "pending",
        "message": "註冊申請已送出，管理員將在 1-3 個工作天內完成審核。"
    }


@router.post("/login", response_model=LoginResponse)
async def login_user(request: LoginRequest):
    """
    使用者登入端點
    
    流程：
    1. 根據 Email 查詢使用者
    2. 驗證密碼
    3. 返回使用者資訊
    """
    def _sync_login(req_email):
        with engine.connect() as conn:
            # 查詢使用者（包含 status）
            user_query = select(
                users_table.c.id,
                users_table.c.email,
                users_table.c.full_name,
                users_table.c.role_id,
                users_table.c.status
            ).where(users_table.c.email == req_email)
            
            user_result = conn.execute(user_query).fetchone()
            
            if not user_result:
                return None, "invalid_credentials"
            
            user_id, email, full_name, role_id, status = user_result
            
            # 檢查帳號狀態
            if status == 'pending':
                return None, "pending"
            elif status == 'rejected':
                return None, "rejected"
            elif status == 'suspended':
                return None, "suspended"
            
            # 查詢密碼
            auth_query = select(user_authentications_table.c.password).where(
                (user_authentications_table.c.user_id == user_id) &
                (user_authentications_table.c.provider == "local")
            )
            auth_result = conn.execute(auth_query).fetchone()
            
            if not auth_result:
                return None, "invalid_credentials"
            
            hashed_password = auth_result[0]
            
            # 查詢角色名稱
            role_query = select(roles_table.c.name).where(roles_table.c.id == role_id)
            role_result = conn.execute(role_query).fetchone()
            role_name = role_result[0] if role_result else "student"
            
            return {
                "user_id": user_id,
                "email": email,
                "full_name": full_name,
                "role": role_name,
                "role_id": role_id,
                "hashed_password": hashed_password
            }, None

    result, error_code = await run_in_db_pool(_sync_login, request.email)
    
    if error_code == "invalid_credentials":
        raise HTTPException(status_code=401, detail="Email 或密碼錯誤")
    elif error_code == "pending":
        raise HTTPException(status_code=403, detail="您的帳號尚未通過審核，請耐心等待管理員處理。")
    elif error_code == "rejected":
        raise HTTPException(status_code=403, detail="您的申請已被拒絕，請聯繫管理員瞭解詳情。")
    elif error_code == "suspended":
        raise HTTPException(status_code=403, detail="您的帳號已被停權，請聯繫管理員。")
    
    # Verify password (CPU bound, fine to run in thread pool but also fast enough here usually)
    # However, since run_in_db_pool wraps run_in_threadpool, we can do it there or here.
    # Doing it here keeps the sync part cleaner (just DB).
    if not verify_password(request.password, result["hashed_password"]):
        raise HTTPException(status_code=401, detail="Email 或密碼錯誤")
    
    # ✅ 生成 JWT token
    access_token = create_access_token(
        user_id=result["user_id"],
        email=result["email"],
        role=result["role"]
    )
    
    # ✅ 記錄登入日誌（純 INSERT，不影響登入流程）
    try:
        def _log_login(uid, rid):
            with engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO user_login_logs (user_id, role_id, logged_in_at)
                    VALUES (:uid, :rid, :now)
                """), {"uid": uid, "rid": rid, "now": get_now_taipei()})
                conn.commit()
        await run_in_db_pool(_log_login, result["user_id"], result["role_id"])
    except Exception:
        pass  # 記錄失敗不影響登入

    return LoginResponse(
        user_id=result["user_id"],
        email=result["email"],
        full_name=result["full_name"],
        role=result["role"],
        access_token=access_token,  # ✅ 返回 token
        token_type="bearer"
    )


# ==================== Token 刷新端點 ====================

@router.post("/refresh-token")
async def refresh_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    """
    刷新 JWT Token（延長登入時間）
    
    允許在 token 過期前或過期後 30 分鐘內刷新。
    返回新的 access_token。
    """
    from jose import JWTError, jwt as jose_jwt
    from backend.app.config.settings import settings as app_settings
    
    try:
        token = credentials.credentials
        # 允許過期 token 在 30 分鐘寬限期內刷新
        try:
            payload = jose_jwt.decode(
                token, app_settings.jwt_secret_key, 
                algorithms=[app_settings.jwt_algorithm]
            )
        except JWTError:
            # Token 過期，嘗試不驗證 exp 來解析
            try:
                payload = jose_jwt.decode(
                    token, app_settings.jwt_secret_key,
                    algorithms=[app_settings.jwt_algorithm],
                    options={"verify_exp": False}
                )
                # 檢查是否在 30 分鐘寬限期內
                exp = payload.get("exp", 0)
                grace_period = 30 * 60  # 30 分鐘
                import time
                if time.time() - exp > grace_period:
                    raise HTTPException(
                        status_code=401,
                        detail="Token 已過期超過寬限期，請重新登入"
                    )
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(
                    status_code=401,
                    detail="無效的 Token，請重新登入"
                )
        
        user_id = payload.get("user_id")
        email = payload.get("email")
        role = payload.get("role")
        
        if not all([user_id, email, role]):
            raise HTTPException(status_code=401, detail="Token payload 不完整")
        
        # 生成新 token
        new_token = create_access_token(
            user_id=user_id,
            email=email,
            role=role
        )
        
        return {
            "access_token": new_token,
            "token_type": "bearer",
            "message": "登入已延長"
        }
        
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Token 刷新失敗，請重新登入"
        )


# ==================== 忘記密碼端點 ====================

class ResetPasswordRequest(BaseModel):
    """重設密碼請求"""
    email: EmailStr = Field(..., description="使用者 Email")
    code: str = Field(..., min_length=6, max_length=6, description="6 位數驗證碼")
    new_password: str = Field(..., min_length=6, description="新密碼 (至少 6 個字元)")


@router.post("/send-password-reset-code")
async def send_password_reset_code(request: SendVerificationCodeRequest):
    """
    發送密碼重設驗證碼到指定 Email
    
    流程：
    1. 檢查 Email 是否已註冊
    2. 生成 6 位數驗證碼
    3. 儲存到資料庫 (有效期 5 分鐘)
    4. 發送密碼重設郵件
    """
    from backend.app.services.email_service import send_password_reset_email

    def _sync_check_and_send(email):
        with engine.connect() as conn:
            # 檢查使用者是否存在
            user_result = conn.execute(
                select(users_table.c.id).where(users_table.c.email == email)
            ).fetchone()
            
            if not user_result:
                return None, "此 Email 尚未註冊"
            
            # 生成驗證碼
            code = generate_verification_code()
            expires_at = get_now_taipei() + timedelta(minutes=5)
            
            # 刪除該 Email 的舊驗證碼
            delete_stmt = delete(email_verifications_table).where(
                email_verifications_table.c.email == email
            )
            conn.execute(delete_stmt)
            
            # 插入新驗證碼
            insert_stmt = insert(email_verifications_table).values(
                email=email,
                code=code,
                expires_at=expires_at,
                created_at=get_now_taipei(),
                is_used=False
            )
            conn.execute(insert_stmt)
            conn.commit()
            return code, None

    code, error = await run_in_db_pool(_sync_check_and_send, request.email)
    
    if error:
        raise HTTPException(status_code=400, detail=error)
    
    success = await run_in_db_pool(send_password_reset_email, request.email, code)
    
    if not success:
        raise HTTPException(status_code=500, detail="發送驗證碼失敗，請稍後再試")
    
    return {"message": "驗證碼已發送至您的信箱", "expires_in_minutes": 5}


@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest):
    """
    重設密碼端點
    
    流程：
    1. 驗證驗證碼是否正確且未過期
    2. 更新使用者密碼
    3. 標記驗證碼為已使用
    """
    hashed_password = hash_password(request.new_password)
    
    def _sync_reset_password(email, code, h_pass):
        with engine.connect() as conn:
            # 查詢驗證碼
            query = select(email_verifications_table).where(
                (email_verifications_table.c.email == email) &
                (email_verifications_table.c.code == code) &
                (email_verifications_table.c.is_used == False) &
                (email_verifications_table.c.expires_at > get_now_taipei())
            )
            result = conn.execute(query).fetchone()
            
            if not result:
                return False, "驗證碼錯誤或已過期"
            
            # 查詢使用者
            user_result = conn.execute(
                select(users_table.c.id).where(users_table.c.email == email)
            ).fetchone()
            
            if not user_result:
                return False, "此 Email 尚未註冊"
            
            user_id = user_result[0]
            
            # 更新密碼
            from sqlalchemy import update
            update_stmt = update(user_authentications_table).where(
                (user_authentications_table.c.user_id == user_id) &
                (user_authentications_table.c.provider == "local")
            ).values(password=h_pass)
            conn.execute(update_stmt)
            
            # 標記驗證碼為已使用
            update_code = update(email_verifications_table).where(
                (email_verifications_table.c.email == email) &
                (email_verifications_table.c.code == code)
            ).values(is_used=True)
            conn.execute(update_code)
            
            conn.commit()
            return True, "密碼重設成功"

    success, message = await run_in_db_pool(
        _sync_reset_password, request.email, request.code, hashed_password
    )
    
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    return {"message": message}
