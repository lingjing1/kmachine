import requests
import json
import time

BASE_URL = "http://localhost:8001/api"
STUDENT_ID = 6  # Default test user
UNIT_ID = 3     # Test Unit (Machine Learning Definitions)
KP_ID = 1       # Test KP (Artificial Intelligence Origins)

def print_step(title):
    print(f"\n{'='*50}")
    print(f"Testing: {title}")
    print(f"{'='*50}")

def test_preview_flow():
    print_step("PREVIEW FLOW")

    # 1. Get Unit KPs
    print(f"GET /student/units/{UNIT_ID}/knowledge-points")
    resp = requests.get(f"{BASE_URL}/student/units/{UNIT_ID}/knowledge-points")
    if resp.status_code == 200:
        print("✅ Get Unit KPs: Success")
        kps = resp.json().get("knowledge_points", [])
        if kps:
            print(f"   Found {len(kps)} KPs. First: {kps[0]['name']}")
    else:
        print(f"❌ Get Unit KPs Failed: {resp.text}")

    # 2. Get KP Questions (Preview)
    print(f"\nGET /student/kps/{KP_ID}/questions")
    resp = requests.get(f"{BASE_URL}/student/kps/{KP_ID}/questions?count=1")
    question_id = None
    if resp.status_code == 200:
        questions_data = resp.json()
        print("✅ Get PV Questions: Success")
        questions = questions_data.get('questions', [])
        if questions:
            q = questions[0]
            question_id = q['id']
            print(f"   Got Question: {q['id']} - {q['question'][:30]}...")
    else:
        print(f"❌ Get PV Questions Failed: {resp.text}")

    # 3. Submit Answer (Preview)
    if question_id:
        print(f"\nPOST /student/question-logs")
        payload = {
            "question_id": question_id,
            "knowledge_point_id": KP_ID,
            "answer": "人工智慧是一種讓電腦模擬人類智慧的技術",
            "stage": "preview"
        }
        resp = requests.post(f"{BASE_URL}/student/question-logs", json=payload)
        if resp.status_code == 200:
            print("✅ Submit PV Answer: Success")
            print(f"   Log ID: {resp.json().get('log_id')}")
        else:
            print(f"❌ Submit PV Answer Failed: {resp.text}")

    # 4. Evaluate Mastery (Preview)
    print(f"\nPOST /student/mastery/kps/{KP_ID}/evaluate (stage=preview)")
    payload = {"stage": "preview"}
    resp = requests.post(f"{BASE_URL}/student/mastery/kps/{KP_ID}/evaluate", json=payload)
    if resp.status_code == 200:
        print("✅ Evaluate Mastery (Preview): Success")
        data = resp.json()
        print(f"   Level: {data.get('mastery_level')}, Confidence: {data.get('confidence_score')}")
    else:
        print(f"❌ Evaluate Mastery (Preview) Failed: {resp.text}")


def test_review_flow():
    print_step("REVIEW FLOW")

    # 1. Get Review Summary
    print(f"GET /student/review/units/{UNIT_ID}/summary")
    resp = requests.get(f"{BASE_URL}/student/review/units/{UNIT_ID}/summary?student_id={STUDENT_ID}")
    if resp.status_code == 200:
        print("✅ Get Review Summary: Success")
        data = resp.json()
        print(f"   Weak Points: {len(data.get('weak_points', []))}")
        print(f"   Personal Quiz: {len(data.get('personal_quiz', []))}")
    else:
        print(f"❌ Get Review Summary Failed: {resp.text}")

    # 2. Get Personal Weak Points
    print(f"\nGET /student/review/units/{UNIT_ID}/weak-points")
    resp = requests.get(f"{BASE_URL}/student/review/units/{UNIT_ID}/weak-points?student_id={STUDENT_ID}")
    if resp.status_code == 200:
        print("✅ Get Weak Points: Success")
        data = resp.json()
        print(f"   Weak Points: {len(data.get('weak_points', []))}")
    else:
        print(f"❌ Get Weak Points Failed: {resp.text}")

    # 3. Get Review Questions (Specific KP)
    print(f"\nGET /student/review/kps/{KP_ID}/questions")
    resp = requests.get(f"{BASE_URL}/student/review/kps/{KP_ID}/questions?student_id={STUDENT_ID}")
    quiz_questions = []
    if resp.status_code == 200:
        print("✅ Get Review Questions: Success")
        data = resp.json()
        quiz_questions = data.get("questions", [])
        print(f"   Found {len(quiz_questions)} questions")
    else:
        print(f"❌ Get Review Questions Failed: {resp.text}")

    # 4. Submit Review Quiz
    if quiz_questions:
        print(f"\nPOST /student/review/units/{UNIT_ID}/quiz")
        answers_payload = [
            {"question_id": q['id'], "kp_id": KP_ID, "is_correct": True} 
            for q in quiz_questions
        ]
        payload = {"answers": answers_payload}
        resp = requests.post(f"{BASE_URL}/student/review/units/{UNIT_ID}/quiz?student_id={STUDENT_ID}", json=payload)
        kp_ids_to_eval = []
        if resp.status_code == 200:
            print("✅ Submit Review Quiz: Success")
            data = resp.json()
            print(f"   Summary: {data.get('summary')}")
            kp_ids_to_eval = data.get('summary', {}).get('kp_ids', [])
            print(f"   KPs to Evaluate: {kp_ids_to_eval}")
        else:
            print(f"❌ Submit Review Quiz Failed: {resp.text}")

        # 5. Evaluate Mastery (Review) - Triggered by frontend based on quiz response
        if kp_ids_to_eval:
            print(f"\nPOST /student/mastery/kps/{kp_ids_to_eval[0]}/evaluate (stage=review)")
            payload = {"stage": "review"}
            resp = requests.post(f"{BASE_URL}/student/mastery/kps/{kp_ids_to_eval[0]}/evaluate", json=payload)
            if resp.status_code == 200:
                print("✅ Evaluate Mastery (Review): Success")
                data = resp.json()
                print(f"   Level: {data.get('mastery_level')}, Confidence: {data.get('confidence_score')}")
            else:
                print(f"❌ Evaluate Mastery (Review) Failed: {resp.text}")

def test_mastery_info():
    print_step("MASTERY INFO")

    # 1. Get Mastery List
    print("GET /student/mastery/list")
    response = requests.get(f"{BASE_URL}/student/mastery/list?course_id=3")
    if response.status_code == 200:
        data = response.json()
        print("✅ Get Mastery List: Success")
        print(f"   Course ID: {data.get('course_id')}")
        print(f"   Masteries Count: {len(data.get('masteries', []))}")
    else:
        print(f"❌ Get Mastery List Failed: {response.text}")

    # 2. Explain Mastery
    print(f"\nGET /student/mastery/kps/{KP_ID}/explain")
    resp = requests.get(f"{BASE_URL}/student/mastery/kps/{KP_ID}/explain?student_id={STUDENT_ID}")
    if resp.status_code == 200:
        print("✅ Explain Mastery: Success")
        data = resp.json()
        print(f"   Keywords: {data.get('keywords')}")
        if data.get('html_report'):
            print("   HTML Report: Present")
    else:
        print(f"❌ Explain Mastery Failed: {resp.text}")


if __name__ == "__main__":
    print(f"Starting API Tests against {BASE_URL}...")
    try:
        # Check server health
        requests.get("http://127.0.0.1:8001/health", timeout=2)
    except:
        print("⚠️ Server might be down or not responding. Proceeding anyway...")
        # exit(1)

    test_preview_flow()
    test_review_flow()
    test_mastery_info()
    print("\nTests Completed.")
