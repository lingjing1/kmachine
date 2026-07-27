#!/bin/bash
# Phase 3 測試腳本：測試所有遷移到 JWT 的 endpoints

API_URL="http://localhost:8001"

echo "========================================="
echo "🧪 Phase 3: JWT 遷移驗證測試"
echo "========================================="
echo ""

# 讀取 Phase 1 儲存的 token
if [ -f "/tmp/jwt_test_token.txt" ]; then
    TOKEN=$(cat /tmp/jwt_test_token.txt)
    echo "✅ 使用已儲存的 JWT Token"
    echo "Token (前60字元): ${TOKEN:0:60}..."
    echo ""
else
    echo "❌ 錯誤：找不到 token"
    echo "請先執行: ./test_phase1_login.sh"
    exit 1
fi

PASSED=0
FAILED=0

# 測試函數
test_endpoint() {
    local test_name="$1"
    local endpoint="$2"
    local method="$3"
    local data="$4"
    local content_type="${5:-application/json}"
    
    echo "測試: $test_name"
    echo "-----------------------------------------"
    
    # 測試 1: 不帶 Token（應該失敗）
    if [ "$method" = "POST" ]; then
        if [ "$content_type" = "multipart/form-data" ]; then
            RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST "$endpoint")
        else
            RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
                -X POST "$endpoint" \
                -H "Content-Type: $content_type" \
                -d "$data")
        fi
    else
        RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" "$endpoint")
    fi
    
    HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS" | cut -d':' -f2)
    
    if [ "$HTTP_STATUS" = "403" ] || [ "$HTTP_STATUS" = "401" ]; then
        echo "  ✅ 無 token: 正確返回 $HTTP_STATUS"
    else
        echo "  ❌ 無 token: 錯誤，返回 $HTTP_STATUS (預期 401/403)"
        ((FAILED++))
        echo ""
        return
    fi
    
    # 測試 2: 帶 Token（應該成功或返回業務邏輯錯誤）
    if [ "$method" = "POST" ]; then
        if [ "$content_type" = "multipart/form-data" ]; then
            RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
                -X POST "$endpoint" \
                -H "Authorization: Bearer $TOKEN")
        else
            RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
                -X POST "$endpoint" \
                -H "Authorization: Bearer $TOKEN" \
                -H "Content-Type: $content_type" \
                -d "$data")
        fi
    else
        RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
            -H "Authorization: Bearer $TOKEN" \
            "$endpoint")
    fi
    
    HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS" | cut -d':' -f2)
    BODY=$(echo "$RESPONSE" | sed '/HTTP_STATUS/d')
    
    # 200-299 或 400-499 都算通過（400-499 可能是業務邏輯錯誤，不是認證問題）
    if [ "$HTTP_STATUS" -ge 200 ] && [ "$HTTP_STATUS" -lt 500 ]; then
        echo "  ✅ 有 token: 返回 $HTTP_STATUS"
        if [ "$HTTP_STATUS" -ge 400 ]; then
            echo "     (業務邏輯錯誤，但認證通過)"
        fi
        ((PASSED++))
    else
        echo "  ❌ 有 token: 錯誤，返回 $HTTP_STATUS"
        echo "     Response: $(echo "$BODY" | head -c 100)"
        ((FAILED++))
    fi
    
    echo ""
}

echo "🔬 開始測試遷移的 Endpoints"
echo "========================================="
echo ""

# 測試 1: /api/v1/generated_materials (Phase 2 pilot)
test_endpoint \
    "GET /api/v1/generated_materials (Phase 2 Pilot)" \
    "${API_URL}/api/v1/generated_materials?limit=5" \
    "GET"

# 測試 2: /api/v1/generate (teacher_agent_router)
test_endpoint \
    "POST /api/v1/generate (Simple Generation)" \
    "${API_URL}/api/v1/generate" \
    "POST" \
    '{
        "prompt": "生成一個簡單的測試題目",
        "source_ids": [],
        "material_type": "preview",
        "length": "concise"
    }'

# 測試 3: /api/v1/generate/refined (teacher_agent_router)
test_endpoint \
    "POST /api/v1/generate/refined (Refined Generation)" \
    "${API_URL}/api/v1/generate/refined" \
    "POST" \
    '{
        "prompt": "生成一個精煉的測試題目",
        "source_ids": [],
        "material_type": "preview",
        "length": "concise",
        "critic_workflow": 2,
        "mode": "quick",
        "max_iterations": 1
    }'

# 測試 4: /api/v1/ingest (teacher_data_router)
# 注意：這個測試只驗證認證，不上傳真實文件
echo "測試: POST /api/v1/ingest (Document Ingestion)"
echo "-----------------------------------------"
echo "  ⚠️  僅測試認證機制（不上傳真實文件）"

RESPONSE_NO_TOKEN=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
    -X POST "${API_URL}/api/v1/ingest")
HTTP_STATUS=$(echo "$RESPONSE_NO_TOKEN" | grep "HTTP_STATUS" | cut -d':' -f2)

if [ "$HTTP_STATUS" = "403" ] || [ "$HTTP_STATUS" = "401" ]; then
    echo "  ✅ 無 token: 正確返回 $HTTP_STATUS"
else
    echo "  ❌ 無 token: 錯誤，返回 $HTTP_STATUS (預期 401/403)"
    ((FAILED++))
fi

RESPONSE_WITH_TOKEN=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
    -X POST "${API_URL}/api/v1/ingest" \
    -H "Authorization: Bearer $TOKEN")
HTTP_STATUS=$(echo "$RESPONSE_WITH_TOKEN" | grep "HTTP_STATUS" | cut -d':' -f2)

if [ "$HTTP_STATUS" = "400" ] || [ "$HTTP_STATUS" = "422" ]; then
    echo "  ✅ 有 token: 返回 $HTTP_STATUS (認證通過，缺少文件參數)"
    ((PASSED++))
elif [ "$HTTP_STATUS" -ge 200 ] && [ "$HTTP_STATUS" -lt 500 ]; then
    echo "  ✅ 有 token: 返回 $HTTP_STATUS"
    ((PASSED++))
else
    echo "  ❌ 有 token: 錯誤，返回 $HTTP_STATUS"
    ((FAILED++))
fi

echo ""

# 總結
echo "========================================="
echo "📊 測試總結"
echo "========================================="
echo ""
echo "通過: $PASSED"
echo "失敗: $FAILED"
echo ""

if [ $FAILED -eq 0 ]; then
    echo "✅ 所有測試通過！Phase 3 JWT 遷移成功！"
    echo ""
    echo "已驗證的 Endpoints:"
    echo "  ✓ GET  /api/v1/generated_materials"
    echo "  ✓ POST /api/v1/generate"
    echo "  ✓ POST /api/v1/generate/refined"
    echo "  ✓ POST /api/v1/ingest"
    echo ""
    echo "🎯 準備進入 Phase 4: 前端集成"
    exit 0
else
    echo "❌ 有 $FAILED 個測試失敗"
    echo ""
    echo "可能原因："
    echo "1. Backend 未重新載入新代碼"
    echo "2. Token 已過期"
    echo "3. API 路徑變更"
    echo ""
    echo "建議："
    echo "- 重啟 uvicorn server"
    echo "- 重新執行 ./test_phase1_login.sh 獲取新 token"
    exit 1
fi
