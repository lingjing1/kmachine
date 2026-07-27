import asyncio
import json
from dotenv import load_dotenv
from backend.app.agents.teacher_agent.critics.quality_critic import QualityCritic
from backend.app.agents.teacher_agent.utils.llm_utils import get_llm

load_dotenv()

async def test_evidence_based_evaluation():
    """
    Test Quality Critic with real generated examples focusing on evidence-based terminology check.
    """
    print("=== Testing Evidence-Based Terminology Evaluation ===\n")
    
    llm = get_llm()
    critic = QualityCritic(llm, threshold=4.0)
    
    # Test Case 1: Good - All terms in evidence
    print("Test Case 1: 優秀 - 所有術語都在 evidence 中")
    print("=" * 70)
    
    good_case = {
        "type": "multiple_choice",
        "questions": [{
            "question_number": 3,
            "question_text": "使用 KNN 算法的目的為何？",
            "options": {
                "A": "刪除重複資料",
                "B": "預測缺失值",
                "C": "降維",
                "D": "數據集成"
            },
            "correct_answer": "B",
            "source": {
                "page_number": "10",
                "evidence": "使用如 KNN（K-Nearest Neighbors）等算法,根據相似記錄來預測缺失值。"
            }
        }]
    }
    
    result1 = await critic.evaluate(good_case, criteria=["Understandable"])
    
    print(f"題目: {good_case['questions'][0]['question_text']}")
    print(f"Evidence: {good_case['questions'][0]['source']['evidence']}\n")
    
    if "evaluations" in result1:
        for eval_item in result1["evaluations"]:
            print(f"📊 評分: {eval_item['rating']}/5 (預期 4-5 分)")
            print(f"分析: {eval_item['analysis'][:150]}...")
            if eval_item.get('suggestions'):
                print(f"建議: {len(eval_item['suggestions'])} 項")
    
    # Test Case 2: Bad -Answer contradicts evidence
    print("\n\n" + "=" * 70)
    print("Test Case 2: 嚴重問題 - 答案與 evidence 矛盾")
    print("=" * 70)
    
    bad_case = {
        "type": "multiple_choice",
        "questions": [{
            "question_number": 5,
            "question_text": "填補缺失值的方式之一是使用什麼來填補年齡？",
            "options": {
                "A": "中位數",
                "B": "平均數",
                "C": "眾數",
                "D": "固定值"
            },
            "correct_answer": "A",
            "source": {
                "page_number": "13",
                "evidence": "年齡 (Age) 列填補為平均值。"
            }
        }]
    }
    
    result2 = await critic.evaluate(bad_case, criteria=["Understandable"])
    
    print(f"題目: {bad_case['questions'][0]['question_text']}")
    print(f"正確答案: A (中位數)")
    print(f"Evidence: {bad_case['questions'][0]['source']['evidence']}")
    print(f"→ 矛盾！Evidence 說的是「平均值」\n")
    
    if "evaluations" in result2:
        for eval_item in result2["evaluations"]:
            print(f"📊 評分: {eval_item['rating']}/5 (預期 1-2 分)")
            print(f"分析: {eval_item['analysis'][:200]}...")
            if eval_item.get('suggestions'):
                print(f"\n建議:")
                for sug in eval_item['suggestions'][:3]:
                    print(f"  - {sug}")
    
    # Test Case 3: Medium - Some terms not in evidence
    print("\n\n" + "=" * 70)
    print("Test Case 3: 中等 - 部分術語未在 evidence 中")
    print("=" * 70)
    
    medium_case = {
        "type": "multiple_choice",
        "questions": [{
            "question_number": 1,
            "question_text": "在資料清洗中，如何處理缺失值？",
            "options": {
                "A": "使用中位數填補所有缺失值",
                "B": "刪除所有包含缺失值的行",
                "C": "使用回歸模型預測填補缺失值",
                "D": "忽視缺失值不做處理"
            },
            "correct_answer": "C",
            "source": {
                "page_number": "10",
                "evidence": "利用其他特徵建立回歸模型來預測缺失值。"
            }
        }]
    }
    
    result3 = await critic.evaluate(medium_case, criteria=["Understandable"])
    
    print(f"題目: {medium_case['questions'][0]['question_text']}")
    print(f"Evidence: {medium_case['questions'][0]['source']['evidence']}")
    print(f"→ 選項 A 提到「中位數」但 evidence 未提及\n")
    
    if "evaluations" in result3:
        for eval_item in result3["evaluations"]:
            print(f"📊 評分: {eval_item['rating']}/5 (預期 3-4 分)")
            print(f"分析: {eval_item['analysis'][:200]}...")
    
    print("\n" + "=" * 70)
    print("✅ 測試完成")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(test_evidence_based_evaluation())
