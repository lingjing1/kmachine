"""
Email 發送服務

提供發送驗證碼郵件的功能，用於學生/教師註冊信箱驗證、密碼重設及教師審核通知。
"""

import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from backend.app.config.settings import settings


def generate_verification_code() -> str:
    """
    生成 6 位數的隨機驗證碼
    
    Returns:
        str: 6 位數字驗證碼
    """
    return ''.join([str(random.randint(0, 9)) for _ in range(6)])


# ==================== 內部共用函數 ====================

def _build_html_email(
    header_title: str,
    body_text: str,
    verification_code: str,
    header_gradient: str = "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
    accent_color: str = "#667eea",
    code_bg_color: str = "#f0f0f0",
) -> str:
    """建立 HTML 格式驗證碼郵件"""
    import uuid
    unique_token = uuid.uuid4().hex
    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: 'Arial', 'Microsoft JhengHei', sans-serif;
            line-height: 1.6;
            color: #333;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f9f9f9;
        }}
        .header {{
            background: {header_gradient};
            color: white;
            padding: 14px 16px;
            text-align: center;
            border-radius: 10px 10px 0 0;
        }}
        .content {{
            background: white;
            padding: 30px;
            border-radius: 0 0 10px 10px;
        }}
        .code-box {{
            background: {code_bg_color};
            border: 2px dashed {accent_color};
            border-radius: 8px;
            padding: 10px;
            text-align: center;
            margin: 20px 0;
        }}
        .code {{
            font-size: 32px;
            font-weight: bold;
            color: {accent_color};
            letter-spacing: 8px;
        }}
        .footer {{
            text-align: center;
            color: #999;
            font-size: 12px;
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{header_title}</h1>
        </div>
        <div class="content">
            <p>您好，</p>
            <p>{body_text}</p>
            
            <div class="code-box">
                <div class="code">{verification_code}</div>
            </div>
            
            <p><strong>注意事項：</strong></p>
            <ul>
                <li>此驗證碼將在 <strong>3 分鐘</strong>後失效</li>
                <li>請勿將驗證碼分享給他人</li>
                <li>如果這不是您的操作，請忽略此郵件</li>
            </ul>
            
            <div class="footer">
                <p>CooK.ai 團隊</p>
                <p><a href="https://coolknowledge.ai/" style="color: #667eea; text-decoration: none;">https://coolknowledge.ai/</a></p>
            </div>
        </div>
    </div>
    <div style="display:none;max-height:0;overflow:hidden;">unique:{unique_token}</div>
</body>
</html>
"""


def _send_email(to_email: str, subject: str, text_content: str, html_content: str) -> bool:
    """
    共用的郵件發送邏輯
    
    Args:
        to_email: 收件人 Email
        subject: 郵件主題
        text_content: 純文字內容
        html_content: HTML 內容
        
    Returns:
        bool: 發送成功返回 True，失敗返回 False
    """
    smtp_host = settings.smtp_host
    smtp_port = settings.smtp_port
    smtp_user = settings.smtp_user
    smtp_password = settings.smtp_password
    
    if not smtp_user or not smtp_password:
        print("錯誤: 未設定 SMTP_USER 或 SMTP_PASSWORD 環境變數")
        return False
    
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = smtp_user
    msg['To'] = to_email
    
    msg.attach(MIMEText(text_content, 'plain', 'utf-8'))
    msg.attach(MIMEText(html_content, 'html', 'utf-8'))
    
    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        
        print(f"郵件已成功發送至 {to_email} (主題: {subject})")
        return True
        
    except Exception as e:
        print(f"發送郵件失敗: {str(e)}")
        return False


# ==================== 對外公開函數 ====================

def send_verification_email(to_email: str, verification_code: str) -> bool:
    """
    發送註冊驗證碼郵件
    
    Args:
        to_email: 收件人 Email
        verification_code: 6 位數驗證碼
        
    Returns:
        bool: 發送成功返回 True，失敗返回 False
    """
    text_content = f"""
您好，

您正在註冊 CooK.ai 學生帳號。

您的驗證碼是: {verification_code}

此驗證碼將在 3 分鐘後失效。

如果這不是您的操作，請忽略此郵件。

CooK.ai 團隊
"""
    
    html_content = _build_html_email(
        header_title="CooK.ai 學生註冊",
        body_text="您正在註冊 CooK.ai 學生帳號。請使用以下驗證碼完成註冊：",
        verification_code=verification_code,
    )
    
    return _send_email(to_email, "CooK.ai 學生註冊驗證碼", text_content, html_content)


def send_teacher_verification_email(to_email: str, verification_code: str) -> bool:
    """
    發送教師註冊驗證碼郵件

    Args:
        to_email: 收件人 Email
        verification_code: 6 位數驗證碼

    Returns:
        bool: 發送成功返回 True，失敗返回 False
    """
    text_content = f"""
您好，

您正在註冊 CooK.ai 教師帳號。

您的驗證碼是: {verification_code}

此驗證碼將在 3 分鐘後失效。

如果這不是您的操作，請忽略此郵件。

CooK.ai 團隊
"""

    html_content = _build_html_email(
        header_title="CooK.ai 教師註冊",
        body_text="您正在註冊 CooK.ai 教師帳號。請使用以下驗證碼完成註冊：",
        verification_code=verification_code,
        header_gradient="linear-gradient(135deg, #1d4ed8 0%, #0ea5e9 100%)",
        accent_color="#1d4ed8",
        code_bg_color="#eff6ff",
    )

    return _send_email(to_email, "CooK.ai 教師註冊驗證碼", text_content, html_content)



def send_password_reset_email(to_email: str, verification_code: str) -> bool:
    """
    發送密碼重設驗證碼郵件
    
    Args:
        to_email: 收件人 Email
        verification_code: 6 位數驗證碼
        
    Returns:
        bool: 發送成功返回 True，失敗返回 False
    """
    text_content = f"""
您好，

您正在重設 CooK.ai 帳號密碼。

您的驗證碼是: {verification_code}

此驗證碼將在 3 分鐘後失效。

如果這不是您的操作，請忽略此郵件，您的密碼不會被更改。

CooK.ai 團隊
"""
    
    html_content = _build_html_email(
        header_title="CooK.ai 密碼重設",
        body_text="您正在重設 CooK.ai 帳號密碼。請使用以下驗證碼完成密碼重設：",
        verification_code=verification_code,
        header_gradient="linear-gradient(135deg, #e67e22 0%, #e74c3c 100%)",
        accent_color="#e67e22",
        code_bg_color="#fff3e0",
    )
    
    return _send_email(to_email, "CooK.ai 密碼重設驗證碼", text_content, html_content)


def _build_html_notification(header_title: str, body_html: str, header_gradient: str, accent_color: str) -> str:
    """建立 HTML 格式通知郵件（無驗證碼區塊）"""
    import uuid
    unique_token = uuid.uuid4().hex
    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: 'Arial', 'Microsoft JhengHei', sans-serif;
            line-height: 1.6;
            color: #333;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f9f9f9;
        }}
        .header {{
            background: {header_gradient};
            color: white;
            padding: 14px 16px;
            text-align: center;
            border-radius: 10px 10px 0 0;
        }}
        .content {{
            background: white;
            padding: 30px;
            border-radius: 0 0 10px 10px;
        }}
        .highlight-box {{
            background: #f0f9f0;
            border-left: 4px solid {accent_color};
            border-radius: 4px;
            padding: 16px 20px;
            margin: 20px 0;
        }}
        .footer {{
            text-align: center;
            color: #999;
            font-size: 12px;
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{header_title}</h1>
        </div>
        <div class="content">
            {body_html}
            <div class="footer">
                <p>CooK.ai 團隊</p>
                <p><a href="https://coolknowledge.ai/" style="color: #667eea; text-decoration: none;">https://coolknowledge.ai/</a></p>
            </div>
        </div>
    </div>
    <div style="display:none;max-height:0;overflow:hidden;">unique:{unique_token}</div>
</body>
</html>
"""


def send_teacher_approval_email(to_email: str, full_name: str) -> bool:
    """
    發送教師審核通過通知郵件

    Args:
        to_email: 教師 Email
        full_name: 教師姓名

    Returns:
        bool: 發送成功返回 True，失敗返回 False
    """
    body_html = f"""
        <p>親愛的 {full_name} 老師，您好，</p>
        <p>感謝您申請加入 CooK.ai 教師平台。我們很高興通知您，您的教師帳號申請已通過審核！</p>
        <div class="highlight-box">
            <p><strong>您現在可以使用以下信箱登入系統：</strong></p>
            <p style="font-size: 16px; margin: 4px 0;">{to_email}</p>
        </div>
        <p>登入後即可開始建立課程、上傳教材，並使用 AI 輔助功能。</p>
        <p>如有任何問題，歡迎透過意見回饋中心與我們聯繫。</p>
    """

    text_content = f"""
親愛的 {full_name} 老師，您好，

感謝您申請加入 CooK.ai 教師平台。您的教師帳號申請已通過審核！

您現在可以使用 {to_email} 登入系統。

登入後即可開始建立課程、上傳教材，並使用 AI 輔助功能。

CooK.ai 團隊
"""

    html_content = _build_html_notification(
        header_title="CooK.ai 教師帳號審核通過",
        body_html=body_html,
        header_gradient="linear-gradient(135deg, #11998e 0%, #38ef7d 100%)",
        accent_color="#11998e",
    )

    return _send_email(to_email, "CooK.ai 教師帳號審核通過通知", text_content, html_content)


def send_teacher_rejection_email(to_email: str, full_name: str, reason: str = "") -> bool:
    """
    發送教師審核拒絕通知郵件

    Args:
        to_email: 教師 Email
        full_name: 教師姓名
        reason: 拒絕原因（可選）

    Returns:
        bool: 發送成功返回 True，失敗返回 False
    """
    reason_block = ""
    reason_text = ""
    if reason:
        reason_block = f"""
        <div class="highlight-box" style="background: #fff3f3; border-left-color: #e74c3c;">
            <p><strong>說明：</strong></p>
            <p>{reason}</p>
        </div>
        """
        reason_text = f"\n拒絕說明：{reason}\n"

    body_html = f"""
        <p>親愛的 {full_name} 老師，您好，</p>
        <p>感謝您申請加入 CooK.ai 教師平台。很遺憾，您的教師帳號申請未能通過本次審核。</p>
        {reason_block}
        <p>若您對結果有疑問，或希望提交更多相關資料重新申請，歡迎透過意見回饋中心與我們聯繫。</p>
    """

    text_content = f"""
親愛的 {full_name} 老師，您好，

感謝您申請加入 CooK.ai 教師平台。很遺憾，您的教師帳號申請未能通過本次審核。{reason_text}
若您對結果有疑問，歡迎透過意見回饋中心與我們聯繫。

CooK.ai 團隊
"""

    html_content = _build_html_notification(
        header_title="CooK.ai 教師帳號審核結果通知",
        body_html=body_html,
        header_gradient="linear-gradient(135deg, #c0392b 0%, #e74c3c 100%)",
        accent_color="#e74c3c",
    )

    return _send_email(to_email, "CooK.ai 教師帳號審核結果通知", text_content, html_content)
