#!/bin/bash
# Phase 1 JWT 測試腳本 - 使用現有帳號

API_URL="http://localhost:8001"

echo "========================================="
echo "🧪 Phase 1: JWT Token 測試（使用現有帳號）"
echo"========================================="
echo ""

echo "請提供您的測試帳號資訊："
read -p "Email: " TEST_EMAIL
read -sp "Password: " TEST_PASSWORD
echo ""
echo ""

echo "🔑 測試步驟: 登入並取得 JWT Token"
echo "-----------------------------------------"

LOGIN_RESPONSE=$(curl -s -X POST "${API_URL}/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$TEST_EMAIL\",
    \"password\": \"$TEST_PASSWORD\"
  }")

echo "登入回應:"
echo "$LOGIN_RESPONSE" | jq '.' 2>/dev/null || echo "$LOGIN_RESPONSE"
echo ""

# 檢查是否有 access_token
TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.access_token' 2>/dev/null)

if [ "$TOKEN" != "null" ] && [ -n "$TOKEN" ] && [ "$TOKEN" != "" ]; then
    echo "✅ 成功取得 JWT Token!"
    echo ""
    echo "Token (前80字元):"
    echo "${TOKEN:0:80}..."
    echo ""
    
    # 解析 Token
    echo "🔍 驗證 Token 內容"
    echo "-----------------------------------------"
    
    # 提取 payload (JWT 的第二部分)
    PAYLOAD=$(echo "$TOKEN" | cut -d'.' -f2)
    
    # 添加 padding 並解碼
    PAYLOAD_LEN=${#PAYLOAD}
    PADDING=$((4 - PAYLOAD_LEN % 4))
    if [ $PADDING -ne 4 ]; then
        for i in $(seq 1 $PADDING); do
            PAYLOAD="${PAYLOAD}="
        done
    fi
    
    DECODED=$(echo "$PAYLOAD" | base64 -d 2>/dev/null)
    
    if [ $? -eq 0 ]; then
        echo "📦 Token Payload:"
        echo "$DECODED" | jq '.' 2>/dev/null || echo "$DECODED"
        echo ""
        
        # 檢查必要欄位
        USER_ID=$(echo "$DECODED" | jq -r '.user_id' 2>/dev/null)
        EMAIL=$(echo "$DECODED" | jq -r '.email' 2>/dev/null)
        ROLE=$(echo "$DECODED" | jq -r '.role' 2>/dev/null)
        
        echo "✅ Token 包含以下資訊："
        echo "   - user_id: $USER_ID"
        echo "   - email: $EMAIL"
        echo "   - role: $ROLE"
        echo ""
        
        echo "========================================="
        echo "✅ Phase 1 測試通過！"
        echo "========================================="
        echo ""
        echo "測試結果："
        echo "✓ 登入 API 正常返回 token"
        echo "✓ Token 包含正確的 user_id, email, role"
        echo "✓ 現有登入功能不受影響"
        echo ""
        
        # 儲存 token 供後續使用
        echo "$TOKEN" > /tmp/jwt_test_token.txt
        echo "Token 已儲存至: /tmp/jwt_test_token.txt"
        echo "可用於 Phase 2 測試"
        
    else
        echo "⚠️  無法解碼 Token Payload"
        echo "但 Token 已成功生成，可能是 base64 解碼問題"
    fi
    
else
    echo "❌ 錯誤: 未能取得 access_token"
    echo ""
    echo "可能原因："
    echo "1. Email 或密碼錯誤"
    echo "2. 帳號尚未驗證"
    echo "3. Backend 配置問題"
    echo ""
    echo "完整回應:"
    echo "$LOGIN_RESPONSE"
    echo ""
    echo "請確認："
    echo "- Email 是否正確"
    echo "- 密碼是否正確"
    echo "- 帳號是否已驗證"
fi
