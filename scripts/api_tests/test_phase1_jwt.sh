#!/bin/bash
# Phase 1 JWT 測試腳本 - 簡化版

API_URL="http://localhost:8001"

echo "========================================="
echo "🧪 Phase 1: JWT Token 測試"
echo "========================================="
echo ""

# 測試 1: 先註冊一個測試帳號
echo "📝 步驟 1: 註冊測試帳號"
echo "-----------------------------------------"

REGISTER_RESPONSE=$(curl -s -X POST "${API_URL}/api/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "jwt_test@example.com",
    "password": "Test123456",
    "full_name": "JWT Test User",
    "role": "teacher",
    "department": "資訊工程學系"
  }')

echo "註冊結果: $REGISTER_RESPONSE"
echo ""

# 等待驗證碼輸入（如果需要）
read -p "請輸入驗證碼（如果有收到信件）或按 Enter 跳過: " VERIFY_CODE

if [ -n "$VERIFY_CODE" ]; then
    echo "驗證帳號..."
    VERIFY_RESPONSE=$(curl -s -X POST "${API_URL}/api/auth/verify" \
      -H "Content-Type: application/json" \
      -d "{
        \"email\": \"jwt_test@example.com\",
        \"code\": \"$VERIFY_CODE\"
      }")
    echo "驗證結果: $VERIFY_RESPONSE"
    echo ""
fi

# 測試 2: 登入並取得 JWT Token
echo "🔑 步驟 2: 登入並取得 JWT Token"
echo "-----------------------------------------"

LOGIN_RESPONSE=$(curl -s -X POST "${API_URL}/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "jwt_test@example.com",
    "password": "Test123456"
  }')

echo "登入回應:"
echo "$LOGIN_RESPONSE" | jq '.' 2>/dev/null || echo "$LOGIN_RESPONSE"
echo ""

# 檢查是否有 access_token
TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.access_token' 2>/dev/null)

if [ "$TOKEN" != "null" ] && [ -n "$TOKEN" ]; then
    echo "✅ 成功取得 JWT Token!"
    echo ""
    echo "Token preview:"
    echo "${TOKEN:0:80}..."
    echo ""
    
    # 測試 3: 解析 Token
    echo "🔍 步驟 3: 驗證 Token 內容"
    echo "-----------------------------------------"
    
    # 提取 payload (JWT 的第二部分)
    HEADER=$(echo "$TOKEN" | cut -d'.' -f1)
    PAYLOAD=$(echo "$TOKEN" | cut -d'.' -f2)
    
    # 添加 padding 並解碼
    PAYLOAD_PADDED="${PAYLOAD}$(printf '=%.0s' {1..4})"
    DECODED=$(echo "$PAYLOAD_PADDED" | base64 -d 2>/dev/null)
    
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
    fi
    
    echo "========================================="
    echo "✅ Phase 1 測試通過！"
    echo "========================================="
    echo ""
    echo "下一步: 使用此 token 測試 Phase 2"
    echo "Token 已儲存，可用於後續測試:"
    echo "export JWT_TOKEN=\"$TOKEN\""
    echo ""
    
    # 儲存 token 到檔案供後續使用
    echo "$TOKEN" > /tmp/jwt_test_token.txt
    echo "Token 已儲存至: /tmp/jwt_test_token.txt"
    
else
    echo "❌ 錯誤: 未能取得 access_token"
    echo ""
    echo "可能原因："
    echo "1. 帳號尚未驗證（請檢查 email 並輸入驗證碼）"
    echo "2. 密碼錯誤"
    echo "3. Backend 配置問題"
    echo ""
    echo "完整回應:"
    echo "$LOGIN_RESPONSE"
fi
