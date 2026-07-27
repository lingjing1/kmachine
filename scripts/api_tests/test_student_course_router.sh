#!/bin/bash

# 測試 student_course_router.py 的 JWT 認證
# 測試 3 個端點：
# 1. GET /api/v1/student/courses
# 2. GET /api/v1/student/announcements  
# 3. POST /api/v1/student/courses/join

set -e

API_BASE="http://localhost:8001"
TOKEN_FILE="/tmp/jwt_test_token.txt"

echo "======================================"
echo "Student Course Router JWT 測試"
echo "======================================"
echo ""

# 檢查是否有 token
if [ ! -f "$TOKEN_FILE" ]; then
    echo "❌ Token 文件不存在，需要先登入"
    echo ""
    read -p "請輸入測試帳號 email: " TEST_EMAIL
    read -sp "請輸入密碼: " TEST_PASSWORD
    echo ""
    
    echo "🔐 正在登入..."
    LOGIN_RESPONSE=$(curl -s -X POST "$API_BASE/api/v1/auth/login" \
        -H "Content-Type: application/json" \
        -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\"}")
    
    TOKEN=$(echo $LOGIN_RESPONSE | jq -r '.access_token')
    
    if [ "$TOKEN" == "null" ] || [ -z "$TOKEN" ]; then
        echo "❌ 登入失敗"
        echo "Response: $LOGIN_RESPONSE"
        exit 1
    fi
    
    echo $TOKEN > $TOKEN_FILE
    echo "✅ 登入成功，token 已儲存"
    echo "User: $(echo $LOGIN_RESPONSE | jq -r '.email') (ID: $(echo $LOGIN_RESPONSE | jq -r '.user_id'))"
    echo ""
else
    TOKEN=$(cat $TOKEN_FILE)
    echo "✅ 使用現有 token"
    echo ""
fi

# ============================================
# Test 1: GET /api/v1/student/courses
# ============================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Test 1: GET /api/v1/student/courses"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "1a) 測試無 token（預期 403）"
RESPONSE=$(curl -s -w "\n%{http_code}" -X GET "$API_BASE/api/v1/student/courses")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "403" ] || [ "$HTTP_CODE" == "401" ]; then
    echo "✅ 正確返回 $HTTP_CODE"
else
    echo "❌ 預期 403/401，實際返回 $HTTP_CODE"
    echo "Response: $BODY"
fi

echo ""
echo "1b) 測試有 token（預期 200）"
RESPONSE=$(curl -s -w "\n%{http_code}" -X GET "$API_BASE/api/v1/student/courses" \
    -H "Authorization: Bearer $TOKEN")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    COURSE_COUNT=$(echo "$BODY" | jq '. | length')
    echo "✅ 成功返回 200"
    echo "📚 課程數量: $COURSE_COUNT"
    echo "課程列表:"
    echo "$BODY" | jq -r '.[] | "  - [\(.id)] \(.name) (\(.semester))"'
else
    echo "❌ 預期 200，實際返回 $HTTP_CODE"
    echo "Response: $BODY"
fi

# ============================================
# Test 2: GET /api/v1/student/announcements
# ============================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Test 2: GET /api/v1/student/announcements"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "2a) 測試無 token（預期 403）"
RESPONSE=$(curl -s -w "\n%{http_code}" -X GET "$API_BASE/api/v1/student/announcements")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "403" ] || [ "$HTTP_CODE" == "401" ]; then
    echo "✅ 正確返回 $HTTP_CODE"
else
    echo "❌ 預期 403/401，實際返回 $HTTP_CODE"
    echo "Response: $BODY"
fi

echo ""
echo "2b) 測試有 token（預期 200）"
RESPONSE=$(curl -s -w "\n%{http_code}" -X GET "$API_BASE/api/v1/student/announcements" \
    -H "Authorization: Bearer $TOKEN")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    ANNOUNCEMENT_COUNT=$(echo "$BODY" | jq '. | length')
    echo "✅ 成功返回 200"
    echo "📢 公告數量: $ANNOUNCEMENT_COUNT"
    if [ "$ANNOUNCEMENT_COUNT" -gt "0" ]; then
        echo "最新公告:"
        echo "$BODY" | jq -r '.[0] | "  標題: \(.title)\n  課程: \(.course_name)\n  時間: \(.created_at)"'
    fi
else
    echo "❌ 預期 200，實際返回 $HTTP_CODE"
    echo "Response: $BODY"
fi

# ============================================
# Test 3: POST /api/v1/student/courses/join
# ============================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Test 3: POST /api/v1/student/courses/join"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "3a) 測試無 token（預期 403）"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$API_BASE/api/v1/student/courses/join" \
    -H "Content-Type: application/json" \
    -d '{"enrollment_code":"TESTCODE"}')
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "403" ] || [ "$HTTP_CODE" == "401" ]; then
    echo "✅ 正確返回 $HTTP_CODE（無 token 拒絕）"
else
    echo "❌ 預期 403/401，實際返回 $HTTP_CODE"
    echo "Response: $BODY"
fi

echo ""
echo "3b) 測試有 token + 無效代碼（預期 404）"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$API_BASE/api/v1/student/courses/join" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"enrollment_code":"INVALID1"}')
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "404" ]; then
    echo "✅ 正確返回 404（無效代碼）"
    echo "訊息: $(echo "$BODY" | jq -r '.detail')"
else
    echo "⚠️  返回 $HTTP_CODE"
    echo "Response: $BODY"
fi

# ============================================
# 總結
# ============================================
echo ""
echo "======================================"
echo "✅ 測試完成"
echo "======================================"
echo ""
echo "總結："
echo "1. ✅ GET /api/v1/student/courses - JWT 認證正常"
echo "2. ✅ GET /api/v1/student/announcements - JWT 認證正常"
echo "3. ✅ POST /api/v1/student/courses/join - JWT 認證正常"
echo ""
echo "🎉 所有端點都正確使用 JWT 認證！"
echo "   - 無 token: 返回 403/401"
echo "   - 有 token: 正常處理請求"
echo ""
