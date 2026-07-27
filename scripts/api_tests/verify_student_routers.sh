#!/bin/bash

# 驗證 Student Routers 的 Auth 修復與功能
# 測試範圍：
# 1. Preview Layout (Material List)
# 2. Preview Questions
# 3. Submission (Assignment)
# 4. Mastery Status
# 5. Review Weak Points

API_BASE="http://localhost:8001"
TOKEN_FILE="/tmp/jwt_test_token.txt"

echo "========================================="
echo "🧪 驗證 Student Routers Auth 修復"
echo "========================================="
echo ""

# 檢查 Token
if [ ! -f "$TOKEN_FILE" ]; then
    echo "❌ 找不到 Token 文件，請先執行 ./test_phase1_login.sh"
    exit 1
fi
TOKEN=$(cat "$TOKEN_FILE")
echo "✅ 使用 Token: ${TOKEN:0:20}..."
echo ""

PASSED=0
FAILED=0

# 測試函數
run_test() {
    local name="$1"
    local method="$2"
    local url="$3"
    local data="$4"
    local expected_status="${5:-200}"

    echo "測試: $name"
    echo "URL: $url"
    
    if [ "$method" == "GET" ]; then
        RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
            -H "Authorization: Bearer $TOKEN" \
            "$url")
    else
        RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
            -X POST \
            -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" \
            -d "$data" \
            "$url")
    fi

    HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS" | cut -d':' -f2)
    BODY=$(echo "$RESPONSE" | sed '/HTTP_STATUS/d')

    if [ "$HTTP_STATUS" == "$expected_status" ]; then
        echo "✅ 通過 (Status: $HTTP_STATUS)"
        ((PASSED++))
    else
        echo "❌ 失敗"
        echo "   預期: $expected_status"
        echo "   實際: $HTTP_STATUS"
        echo "   回應: $(echo "$BODY" | head -c 200)..."
        ((FAILED++))
    fi
    echo "-----------------------------------------"
    echo ""
}

# 1. 測試教材列表 (原問題點)
# 假設 unit_id=1 存在
run_test "教材列表 (Preview Material List)" \
    "GET" \
    "$API_BASE/api/student/units/1/contents" \
    "" \
    "200"

# 2. 測試獲取題目 (Preview Questions)
# 假設 kp_id=1 存在
run_test "獲取題目 (Fetch Questions)" \
    "GET" \
    "$API_BASE/api/student/questions?kp_id=1&count=1" \
    "" \
    "200"

# 3. 測試提交作業 (Submission)
# 假設 content_id=1 是一個 assignment
# 注意：若 content_id 不存在或不是 assignment，可能會返回 404 或 400，但 Auth 應該要過 (不會是 401/403/500 Type Error)
# 我們主要驗證是否會報 TypeError: get_current_user_id() got an unexpected keyword argument
# 如果返回 404 (Content not found) 也算 Auth 通過
# 為了保險，這裡我們放寬檢查：只要不是 500 且不是 403 就算 Auth fixed
# 但 run_test 目前只檢查 exact match。我們手動檢查一下結果。

echo "測試: 提交作業 (Submit Assignment - Auth Check)"
echo "URL: $API_BASE/api/student/assignments/9999/submit"
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
    -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"answers": [], "started_at": "2023-01-01T00:00:00Z"}' \
    "$API_BASE/api/student/assignments/9999/submit")

HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS" | cut -d':' -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_STATUS/d')

if [ "$HTTP_STATUS" == "404" ] || [ "$HTTP_STATUS" == "400" ] || [ "$HTTP_STATUS" == "200" ]; then
    echo "✅ 通過 (Status: $HTTP_STATUS) - Auth 成功，邏輯層返回預期錯誤或成功"
    ((PASSED++))
elif [ "$HTTP_STATUS" == "500" ]; then
    echo "❌ 失敗 (Status: 500) - 可能是 TypeError 仍存在"
    echo "Response: $BODY"
    ((FAILED++))
else 
    echo "⚠️  未知狀態: $HTTP_STATUS"
    echo "Response: $BODY"
    ((FAILED++))
fi
echo "-----------------------------------------"
echo ""

# 4. 測試 Mastery Status
run_test "Mastery Status" \
    "GET" \
    "$API_BASE/api/student/mastery/kps/1/status" \
    "" \
    "200"

# 5. 測試 Review Weak Points
# 假設 unit_id=1
run_test "Review Weak Points" \
    "GET" \
    "$API_BASE/api/student/review/units/1/weak-points" \
    "" \
    "200"

echo "========================================="
echo "📊 總結"
echo "通過: $PASSED"
echo "失敗: $FAILED"
echo "========================================="

if [ $FAILED -eq 0 ]; then
    exit 0
else
    exit 1
fi
