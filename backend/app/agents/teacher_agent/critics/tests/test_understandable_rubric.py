import asyncio
import json
from dotenv import load_dotenv
from backend.app.agents.teacher_agent.critics.quality_critic import QualityCritic
from backend.app.agents.teacher_agent.utils.llm_utils import get_llm

load_dotenv()

async def test_understandable_rubric():
    """
    Test the enhanced Understandable rubric with edge cases:
    1. Lack of context
    2. Inappropriate use of advanced terminology
    """
    print("=== Testing Enhanced 'Understandable' Rubric ===\n")
    
    llm = get_llm()
    critic = QualityCritic(llm, threshold=4.0)
    
    # Test Case 1: No context + Many undefined terms (應該得 1-2 分)
    print("Test Case 1: 缺乏情境 + 大量未定義術語")
    print("=" * 70)
    
    case1 = {
        "type": "multiple_choice",
        "questions": [{
            "question_number": 1,
            "question_text": "下列關於 Backpropagation 中的梯度消失問題，何者正確？",
            "options": {
                "A": "使用 ReLU 可完全避免",
                "B": "與 Sigmoid 的導數範圍有關",
                "C": "只出現在 RNN 中",
                "D": "可透過 Batch Normalization 解決"
            },
            "correct_answer": "B",
            "source": {
                "page_number": "1",
                "evidence": "梯度消失是深度學習訓練中的常見問題。"
            }
        }]
    }
    
    result1 = await critic.evaluate(case1, criteria=["Understandable"])
   
    print(f"\n評估結果:")
    print(json.dumps(result1, ensure_ascii=False, indent=2))
    
    if "evaluations" in result1:
        for eval_item in result1["evaluations"]:
            print(f"\n📊 {eval_item['criteria']}")
            print(f"   評分: {eval_item['rating']}/5")
            print(f"   分析: {eval_item['analysis']}")
            if eval_item.get('suggestions'):
                print(f"   建議:")
                for sug in eval_item['suggestions']:
                    print(f"      - {sug}")
    
    # Test Case 2: Minimal context + Some undefined terms (應該得 2-3 分)
    print("\n\n" + "=" * 70)
    print("Test Case 2: 情境不足 + 部分未定義術語")
    print("=" * 70)
    
    case2 = {
        "type": "multiple_choice",
        "questions": [{
            "question_number": 1,
            "question_text": "在數據預處理階段，標準化（Standardization）的目的為何？",
            "options": {
                "A": "將數據轉換為 0-1 範圍",
                "B": "移除異常值",
                "C": "使數據均值為 0，標準差為 1",
                "D": "增加數據維度"
            },
            "correct_answer": "C",
            "source": {
                "page_number": "1",
                "evidence": "標準化是常用的數據預處理技術。"
            }
        }]
    }
    
    result2 = await critic.evaluate(case2, criteria=["Understandable"])
    
    print(f"\n評估結果:")
    print(json.dumps(result2, ensure_ascii=False, indent=2))
    
    if "evaluations" in result2:
        for eval_item in result2["evaluations"]:
            print(f"\n📊 {eval_item['criteria']}")
            print(f"   評分: {eval_item['rating']}/5")
            print(f"   分析: {eval_item['analysis']}")
            if eval_item.get('suggestions'):
                print(f"   建議:")
                for sug in eval_item['suggestions']:
                    print(f"      - {sug}")
    
    # Test Case 3: Good context + Clear definitions (應該得 4-5 分)
    print("\n\n" + "=" * 70)
    print("Test Case 3: 充足情境 + 清楚定義")
    print("=" * 70)
    
    case3 = {
        "type": "multiple_choice",
        "questions": [{
            "question_number": 1,
            "question_text": """小明想要建立一個預測房價的模型。他收集了 500 筆房屋資料，每筆資料包含 20 個特徵（如：坪數、房間數、屋齡等）。
但他發現，許多特徵之間高度相關（例如：坪數與房間數），這會讓模型變得複雜且難以解釋。

為了簡化模型，小明決定使用「主成分分析（PCA）」。PCA 的核心概念是：
找出資料中最重要的「方向」（稱為主成分），將原本 20 個特徵壓縮成 3-5 個主成分，
同時保留 95% 以上的資訊量。

根據以上情境，PCA 在小明的案例中主要解決了什麼問題？""",
            "options": {
                "A": "增加房屋特徵的數量，讓模型更準確",
                "B": "減少特徵維度，降低模型複雜度",
                "C": "自動找出房價最高的房屋",
                "D": "將房間數轉換為坪數"
            },
            "correct_answer": "B",
            "source": {
                "page_number": "1",
                "evidence": "PCA 是降維技術，用於簡化高維數據。"
            }
        }]
    }
    
    result3 = await critic.evaluate(case3, criteria=["Understandable"])
    
    print(f"\n評估結果:")
    print(json.dumps(result3, ensure_ascii=False, indent=2))
    
    if "evaluations" in result3:
        for eval_item in result3["evaluations"]:
            print(f"\n📊 {eval_item['criteria']}")
            print(f"   評分: {eval_item['rating']}/5")
            print(f"   分析: {eval_item['analysis']}")
            if eval_item.get('suggestions'):
                print(f"   建議:")
                for sug in eval_item['suggestions']:
                    print(f"      - {sug}")
    
    print("\n" + "=" * 70)
    print("✅ Rubric 測試完成!")
    print("=" * 70)
    
    # Summary
    print("\n📊 評分總結:")
    if "evaluations" in result1:
        print(f"  Case 1 (無情境+多術語): {result1['evaluations'][0]['rating']}/5 - 預期 1-2 分")
    if "evaluations" in result2:
        print(f"  Case 2 (情境不足+部分術語): {result2['evaluations'][0]['rating']}/5 - 預期 2-3 分")
    if "evaluations" in result3:
        print(f"  Case 3 (充足情境+清楚定義): {result3['evaluations'][0]['rating']}/5 - 預期 4-5 分")

if __name__ == "__main__":
    asyncio.run(test_understandable_rubric())
