import asyncio
import json
from dotenv import load_dotenv
from backend.app.agents.teacher_agent.critics.quality_critic import QualityCritic
from backend.app.agents.teacher_agent.utils.llm_utils import get_llm

load_dotenv()

async def test_quality_critic_geval():
    """
    Test optimized Quality Critic with G-Eval framework.
    Validates: Analyze-Rate-Suggest strategy, LLM-generated suggestions, error handling.
    """
    print("=== Testing G-Eval Quality Critic (Optimized Version) ===\n")
    
    # Initialize LLM
    llm = get_llm()
    
    # Initialize critic with threshold=4.0
    critic = QualityCritic(llm, threshold=4.0)
    
    # Test Case 1: High quality content (should get high scores, no suggestions)
    print("Test Case 1: High Quality Content")
    print("-" * 70)
    
    high_quality_content = {
        "type": "multiple_choice",
        "questions": [
            {
                "question_number": 1,
                "question_text": "PCA（主成分分析）的主要目的為何？",
                "options": {
                    "A": "增加資料的維度",
                    "B": "降維以簡化資料分析",
                    "C": "同時處理多個資料來源",
                    "D": "提高資料的準確性"
                },
                "correct_answer": "B",
                "source": {
                    "page_number": "25",
                    "evidence": "PCA的主要用途是將資料降維到較少的主要成分，以簡化資料的分析。"
                }
            }
        ]
    }
    
    result1 = await critic.evaluate(high_quality_content)
    
    print(f"Evaluation Result:")
    print(json.dumps(result1, ensure_ascii=False, indent=2))
    
    if "evaluations" in result1:
        print(f"\n📊 Summary:")
        avg_score = sum(e["rating"] for e in result1["evaluations"]) / len(result1["evaluations"])
        print(f"Average Score: {avg_score:.2f}/5.0")
        
        has_suggestions = any("suggestions" in e and e["suggestions"] for e in result1["evaluations"])
        print(f"Has Suggestions: {'✅ Yes' if has_suggestions else '❌ No (all scores >= threshold)'}")
    
    # Test Case 2: Low quality content (大陸用語, 語法錯誤)
    print("\n\n" + "=" * 70)
    print("Test Case 2: Low Quality Content (Should Trigger Suggestions)")
    print("-" * 70)
    
    low_quality_content = {
        "type": "multiple_choice",
        "questions": [
            {
                "question_number": 1,
                "question_text": "机器学习中的数据预处理包括哪些步驟？",  # 簡體字
                "options": {
                    "A": "数据清洗和标准化",  # 簡體字
                    "B": "数据可视化",
                    "C": "模型訓練",
                    "D": "以上皆是"
                },
                "correct_answer": "A",
                "source": {
                    "page_number": "15",
                    "evidence": "数据预处理是机器学习流程中的重要步骤。"
                }
            }
        ]
    }
    
    result2 = await critic.evaluate(low_quality_content)
    
    print(f"Evaluation Result:")
    print(json.dumps(result2, ensure_ascii=False, indent=2))
    
    if "evaluations" in result2:
        print(f"\n📊 Summary:")
        avg_score = sum(e["rating"] for e in result2["evaluations"]) / len(result2["evaluations"])
        print(f"Average Score: {avg_score:.2f}/5.0")
        
        suggestions_count = sum(len(e.get("suggestions", [])) for e in result2["evaluations"])
        print(f"Total Suggestions: {suggestions_count}")
        
        if suggestions_count > 0:
            print("\n💡 LLM-Generated Suggestions:")
            for i, eval_item in enumerate(result2["evaluations"], 1):
                if "suggestions" in eval_item and eval_item["suggestions"]:
                    print(f"\n  [{i}] {eval_item['criteria']} (Score: {eval_item['rating']}/5)")
                    for j, sug in enumerate(eval_item["suggestions"], 1):
                        print(f"      {j}. {sug}")
    
    # Test Case 3: Batch evaluation
    print("\n\n" + "=" * 70)
    print("Test Case 3: Batch Evaluation (2 items)")
    print("-" * 70)
    
    batch_content = [high_quality_content, low_quality_content]
    batch_results = await critic.batch_evaluate(batch_content)
    
    print(f"Batch Results: {len(batch_results)} items evaluated")
    for i, res in enumerate(batch_results, 1):
        if "evaluations" in res:
            avg = sum(e["rating"] for e in res["evaluations"]) / len(res["evaluations"])
            sug_count = sum(len(e.get("suggestions", [])) for e in res["evaluations"])
            print(f"  Item {i}: Avg Score = {avg:.2f}, Suggestions = {sug_count}")
    
    print("\n" + "=" * 70)
    print("✅ G-Eval Quality Critic Test Complete!")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(test_quality_critic_geval())
