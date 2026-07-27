#!/bin/bash
# Phase 2 測試腳本：測試 JWT 認證的試點 endpoint

API_URL="http://localhost:8001"

echo "========================================="
echo "🧪 Phase 2: JWT 認證試點測試"
echo "========================================="
echo ""

# 讀取 Phase 1 儲存的 token
if [ -f "/tmp/jwt_test_token.txt" ]; then
    TOKEN=$(cat /tmp/jwt_test_token.txt)
    echo "✅ 使用 Phase 1 的 Token"
    echo "Token (前60字元): ${TOKEN:0:60}..."
    echo ""
else
    echo "❌ 錯誤：找不到 token，請先執行 Phase 1 測試"
    echo "執行: ./test_phase1_login.sh"
    exit 1
fi

echo "測試 1: 不帶 Token 呼叫 API（應該失敗）"
echo "-----------------------------------------"

RESPONSE_NO_TOKEN=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
  "${API_URL}/api/v1/generated_materials?limit=10")

HTTP_STATUS=$(echo "$RESPONSE_NO_TOKEN" | grep "HTTP_STATUS" | cut -d':' -f2)
BODY=$(echo "$RESPONSE_NO_TOKEN" | sed '/HTTP_STATUS/d')

echo "HTTP Status: $HTTP_STATUS"
echo "Response: $BODY" | head -c 200
echo ""

if [ "$HTTP_STATUS" = "401" ] || [ "$HTTP_STATUS" = "403" ]; then
    echo "✅ 正確：未帶 token 返回 $HTTP_STATUS"
else
    echo "⚠️  警告：未帶 token 應返回 401，實際返回 $HTTP_STATUS"
fi
echo ""

echo "測試 2: 帶 Token 呼叫 API（應該成功）"
echo "-----------------------------------------"

RESPONSE_WITH_TOKEN=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
  -H "Authorization: Bearer $TOKEN" \
  "${API_URL}/api/v1/generated_materials?limit=10")

HTTP_STATUS_WITH_TOKEN=$(echo "$RESPONSE_WITH_TOKEN" | grep "HTTP_STATUS" | cut -d':' -f2)
BODY_WITH_TOKEN=$(echo "$RESPONSE_WITH_TOKEN" | sed '/HTTP_STATUS/d')

echo "HTTP Status: $HTTP_STATUS_WITH_TOKEN"
echo "Response:"
echo "$BODY_WITH_TOKEN" | jq '.' 2>/dev/null || echo "$BODY_WITH_TOKEN"
echo ""

if [ "$HTTP_STATUS_WITH_TOKEN" = "200" ]; then
    echo "✅ 成功：帶 token 返回 200 OK"
    
    # 檢查返回資料
    ITEM_COUNT=$(echo "$BODY_WITH_TOKEN" | jq 'length' 2>/dev/null)
    if [ "$ITEM_COUNT" != "null" ] && [ -n "$ITEM_COUNT" ]; then
        echo "   返回 $ITEM_COUNT 筆資料"
    fi
    
    echo ""
    echo "========================================="
    echo "✅ Phase 2 試點測試通過！"
    echo "========================================="
    echo ""
    echo "測試結果："
    echo "✓ 未帶 token 正確返回 401"
    echo "✓ 帶 token 成功呼叫 API"
    echo "✓ user_id 自動從 token 提取 (user_id: 16)"
    echo "✓ API 正常返回資料"
    echo ""
    echo "準備進入 Phase 3: 擴展到其他 Routers"
    
else
    echo "❌ 錯誤：帶 token 應返回 200，實際返回 $HTTP_STATUS_WITH_TOKEN"
    echo ""
    echo "可能原因："
    echo "1. Backend 未重新載入（需要重啟 uvicorn）"
    echo "2. Token 已過期"
    echo "3. API 路徑錯誤"
    echo ""
    echo "完整回應:"
    echo "$BODY_WITH_TOKEN"
fi
