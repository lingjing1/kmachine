"""
插入測試資料：student_knowledge_mastery 和 student_chatbot_dialogs
"""
import os
import json
from sqlalchemy import create_engine, text as sql_text
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime
import uuid

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

engine = create_engine(DATABASE_URL)
openai_client = OpenAI(api_key=OPENAI_API_KEY, timeout=30.0)

def get_embedding(text: str):
    """生成 embedding"""
    response = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding

def to_pgvector_str(vec):
    """轉換為 pgvector 格式"""
    return "[" + ",".join(f"{x:.8f}" for x in vec) + "]"

def insert_test_data():
    """插入測試資料"""
    with engine.begin() as conn:
        # 優先使用 student_id = 6，不存在則查詢第一個學生
        student = conn.execute(sql_text("SELECT id FROM users WHERE id = :uid"), {"uid": 6}).fetchone()
        if not student:
            student = conn.execute(sql_text("SELECT id FROM users WHERE role_id = 2 LIMIT 1")).fetchone()
        
        if not student:
            print("❌ 找不到學生資料")
            return
        
        student_id = student[0]
        print(f"✅ 使用學生 ID: {student_id}")
        
        # 查詢課程 ID = 3 的相關資料
        course_id = 3
        
        # 查詢該課程的前 3 個知識點
        kps = conn.execute(sql_text("""
            SELECT id, unit_id, name 
            FROM knowledge_points 
            WHERE course_id = :cid 
            LIMIT 3
        """), {"cid": course_id}).fetchall()
        
        if not kps:
            print("❌ 找不到知識點資料")
            return
        
        print(f"✅ 找到 {len(kps)} 個知識點")
        
        # === 1. 插入 student_knowledge_mastery ===
        print("\n📊 插入 student_knowledge_mastery...")
        
        mastery_levels = ["待加強", "尚可", "精熟"]
        
        for idx, kp in enumerate(kps):
            kp_id = kp[0]
            unit_id = kp[1]
            kp_name = kp[2]
            level = mastery_levels[idx % 3]
            
            # 檢查是否已存在（嚴格比對所有 key）
            exists = conn.execute(sql_text("""
                SELECT 1 FROM student_knowledge_mastery 
                WHERE student_id = :sid AND course_id = :cid 
                  AND unit_id = :uid AND knowledge_point_id = :kpid
            """), {"sid": student_id, "cid": course_id, "uid": unit_id, "kpid": kp_id}).fetchone()
            
            if exists:
                print(f"   ⚠️  KP {kp_id} ({kp_name}) 已有精熟度記錄，跳過")
                continue
            
            conn.execute(sql_text("""
                INSERT INTO student_knowledge_mastery 
                (student_id, course_id, unit_id, knowledge_point_id, mastery_level, 
                 preview_completed, review_completed)
                VALUES (:sid, :cid, :uid, :kpid, :level, :prev, :rev)
            """), {
                "sid": student_id,
                "cid": course_id,
                "uid": unit_id,
                "kpid": kp_id,
                "level": level,
                "prev": idx == 0,  # 第一個已完成 preview
                "rev": idx == 2    # 第三個已完成 review
            })
            
            print(f"   ✅ 插入 KP {kp_id} ({kp_name}): {level}")
        
        # === 2. 插入 student_chatbot_dialogs ===
        print("\n💬 插入 student_chatbot_dialogs...")
        
        # 定義多組對話（涵蓋不同知識點和主題）
        conversations = [
            {
                "id": "test-conversation-001",
                "kp_idx": 0,  # 第一個知識點
                "dialogs": [
                    {"role": "user", "text": "什麼是監督式學習？"},
                    {"role": "assistant", "text": "監督式學習是機器學習的一種方法，其中模型從標記好的訓練資料中學習。透過大量的輸入-輸出配對範例，模型學會從輸入預測正確的輸出。"},
                    {"role": "user", "text": "它跟非監督式學習有什麼不同？"},
                    {"role": "assistant", "text": "監督式學習需要標記好的資料（有正確答案），而非監督式學習則是從未標記的資料中尋找模式。就像監督式是有老師教學，非監督式是自己探索發現規律。"}
                ]
            },
            {
                "id": "test-conversation-002",
                "kp_idx": 1,  # 第二個知識點
                "dialogs": [
                    {"role": "user", "text": "監督式學習有哪些常用的演算法？"},
                    {"role": "assistant", "text": "常見的監督式學習演算法包括：線性回歸、邏輯回歸、決策樹、隨機森林、支持向量機(SVM)、K近鄰(KNN)和神經網路等。每種演算法都有其適用的場景。"},
                    {"role": "user", "text": "決策樹為什麼容易過擬合？"},
                    {"role": "assistant", "text": "決策樹如果長得太深，會記住訓練資料的每個細節，包括噪音。這就像背答案而不是理解概念，導致在新資料上表現不佳。我們可以透過剪枝、限制深度等方法來避免。"}
                ]
            },
            {
                "id": "test-conversation-003",
                "kp_idx": 2,  # 第三個知識點
                "dialogs": [
                    {"role": "user", "text": "特徵工程是什麼？為什麼重要？"},
                    {"role": "assistant", "text": "特徵工程是從原始資料中提取和創建有用特徵的過程。好的特徵可以大幅提升模型效能，就像給模型更好的「工具」來理解資料。"},
                    {"role": "user", "text": "可以舉個例子嗎？"},
                    {"role": "assistant", "text": "例如預測房價時，除了使用房間數量，我們可以創造「房間數/坪數」這個新特徵來表示空間使用效率。這個衍生特徵可能比原始特徵更有預測力。"}
                ]
            },
            {
                "id": "test-conversation-004",
                "kp_idx": 0,  # 循環回第一個
                "dialogs": [
                    {"role": "user", "text": "cross-validation 是什麼？"},
                    {"role": "assistant", "text": "Cross-validation（交叉驗證）是評估模型泛化能力的技術。我們把資料分成多份，輪流用不同份當測試集，這樣可以更可靠地評估模型表現。"},
                    {"role": "user", "text": "為什麼不直接用一個測試集就好？"},
                    {"role": "assistant", "text": "單一測試集可能剛好運氣好或運氣差。交叉驗證讓每筆資料都有機會當測試集，結果更穩定可靠，也能充分利用有限的資料。"}
                ]
            },
            {
                "id": "test-conversation-005",
                "kp_idx": 1,  # 第二個知識點
                "dialogs": [
                    {"role": "user", "text": "overfitting 和 underfitting 的差別？"},
                    {"role": "assistant", "text": "Overfitting（過擬合）是模型太複雜，記住了訓練資料的噪音；underfitting（欠擬合）是模型太簡單，連基本規律都學不會。就像考試：過擬合是死記答案，欠擬合是沒讀懂課本。"}
                ]
            }
        ]
        
        inserted_count = 0
        skipped_count = 0
        
        for conv in conversations:
            conv_id = conv["id"]
            kp = kps[conv["kp_idx"]]
            kp_id = kp[0]
            unit_id = kp[1]
            
            # 檢查是否已存在該對話
            existing = conn.execute(sql_text("""
                SELECT 1 FROM student_chatbot_dialogs 
                WHERE conversation_id = :conv_id LIMIT 1
            """), {"conv_id": conv_id}).fetchone()
            
            if existing:
                print(f"   ⚠️  對話 {conv_id} 已存在，跳過")
                skipped_count += 1
                continue
            
            # 插入對話
            for dialog in conv["dialogs"]:
                msg_text = dialog["text"]
                embedding = get_embedding(msg_text)
                
                content = {"message": msg_text, "type": "text"}
                
                conn.execute(sql_text("""
                    INSERT INTO student_chatbot_dialogs
                    (student_id, course_id, unit_id, knowledge_point_id, conversation_id, 
                     role, content, content_embedding)
                    VALUES (:sid, :cid, :uid, :kpid, :conv_id, :role, (:content)::jsonb, (:embedding)::vector)
                """), {
                    "sid": student_id,
                    "cid": course_id,
                    "uid": unit_id,
                    "kpid": kp_id,
                    "conv_id": conv_id,
                    "role": dialog["role"],
                    "content": json.dumps(content, ensure_ascii=False),
                    "embedding": to_pgvector_str(embedding)
                })
            
            inserted_count += 1
            print(f"   ✅ 插入對話 {conv_id} ({len(conv['dialogs'])} 則訊息)")
        
        print(f"\n   📊 對話統計: {inserted_count} 組新增, {skipped_count} 組跳過")
        
        print("\n" + "="*60)
        print("✅ 測試資料插入完成！")
        print("="*60)

if __name__ == "__main__":
    insert_test_data()
