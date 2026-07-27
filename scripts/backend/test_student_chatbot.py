import requests
import json
import sys
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# Configuration
API_URL = "http://localhost:8002/api/v1/student/chatbot/messages"

def get_sample_data():
    """從資料庫查詢實際存在的測試資料"""
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        # 查詢第一個 student (role_id = 2)
        student_query = "SELECT id FROM users WHERE role_id = 2 LIMIT 1"
        student = conn.execute(text(student_query)).fetchone()
        
        if not student:
            print("❌ 資料庫中沒有學生資料")
            return None
            
        student_id = student[0]
        
        # 查詢第一個 course
        course_query = "SELECT id FROM courses LIMIT 1"
        course = conn.execute(text(course_query)).fetchone()
        
        if not course:
            print("❌ 資料庫中沒有課程資料")
            return None
            
        course_id = course[0]
        
        # 查詢該課程的第一個 unit
        unit_query = "SELECT id FROM course_units WHERE course_id = :course_id AND id = 3 LIMIT 1"  # 查詢 unit_id=3（測試資料所在）
        unit = conn.execute(text(unit_query), {"course_id": course_id}).fetchone()
        
        unit_id = unit[0] if unit else None
        
        # 查詢該 unit 的第一個 knowledge_point
        kp_id = None
        if unit_id:
            kp_query = "SELECT id FROM knowledge_points WHERE unit_id = :unit_id LIMIT 1"
            kp = conn.execute(text(kp_query), {"unit_id": unit_id}).fetchone()
            kp_id = kp[0] if kp else None
        
        return {
            "student_id": student_id,
            "course_id": course_id,
            "unit_id": unit_id,
            "knowledge_point_id": kp_id
        }

def test_send_message(message=None, course_id=None, unit_id=None, kp_id=None, student_id=None):
    """測試發送訊息到 student chatbot"""
    print("=== Testing Student Chatbot API ===\n")
    
    # 如果沒有提供參數，從資料庫查詢
    if course_id is None:
        print("📊 從資料庫查詢測試資料...")
        data = get_sample_data()
        if not data:
            return
        
        course_id = data["course_id"]
        unit_id = data["unit_id"]
        kp_id = data["knowledge_point_id"]
        
        print(f"✅ 查詢到資料:")
        print(f"  - Course ID: {course_id}")
        print(f"  - Unit ID: {unit_id}")
        print(f"  - Knowledge Point ID: {kp_id}\n")
    
    # 預設測試訊息
    if message is None:
        message = "什麼是監督式學習？"
    
    # 構建請求
    payload = {
        "message": message,
        "course_id": course_id,
    }
    
    if unit_id:
        payload["unit_id"] = unit_id
    if kp_id:
        payload["knowledge_point_id"] = kp_id
    if student_id:
        payload["student_id"] = student_id
    
    print(f"📤 發送請求:")
    print(f"URL: {API_URL}")
    print(f"Payload:\n{json.dumps(payload, indent=2, ensure_ascii=False)}\n")
    
    try:
        response = requests.post(API_URL, json=payload, timeout=30)
        
        print(f"📥 收到回應:")
        print(f"Status Code: {response.status_code}\n")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ API 呼叫成功!")
            print(f"\n完整回應:\n{json.dumps(data, indent=2, ensure_ascii=False)}")
            
            # 提取關鍵資訊
            print(f"\n--- 摘要 ---")
            print(f"Conversation ID: {data.get('conversation_id')}")
            print(f"User Message ID: {data.get('user_message_id')}")
            print(f"Assistant Message ID: {data.get('assistant_message_id')}")
            print(f"\n助理回應:\n{data.get('assistant_response')}")
            
            metadata = data.get('metadata')
            if metadata:
                print(f"\nMetadata:")
                print(f"  - Strategy: {metadata.get('scaffolding_strategy')}")
                print(f"  - Sources Count: {metadata.get('sources_count')}")
                
        else:
            print(f"❌ API 請求失敗")
            print(f"Error Response:\n{response.text}")
            
    except requests.exceptions.Timeout:
        print("❌ 請求超時（30秒）")
    except requests.exceptions.ConnectionError:
        print("❌ 無法連接到 API server，請確認 uvicorn 是否正在運行")
    except Exception as e:
        print(f"❌ 發生錯誤: {e}")

if __name__ == "__main__":
    # 支援命令行參數
    # 用法: python test_student_chatbot.py [message] [course_id] [unit_id] [kp_id]
    
    message = sys.argv[1] if len(sys.argv) > 1 else None
    course_id = int(sys.argv[2]) if len(sys.argv) > 2 else None
    unit_id = int(sys.argv[3]) if len(sys.argv) > 3 else None
    kp_id = int(sys.argv[4]) if len(sys.argv) > 4 else None
    student_id = int(sys.argv[5]) if len(sys.argv) > 5 else None
    
    test_send_message(message, course_id, unit_id, kp_id, student_id)
