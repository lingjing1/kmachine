// frontend/src/components/auth/SessionExpiryWarning.tsx
import { useEffect, useState, useCallback, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { useUser } from '../../contexts/UserContext';
import API_BASE_URL from '../../config/api';

/** 公開頁面（無需登入），不顯示過期警告 */
const PUBLIC_PATHS = ['/'];

/**
 * 解析 JWT token 的 payload（不驗證簽名，僅讀取 exp）
 */
function parseJwtExp(token: string): number | null {
    try {
        const base64Payload = token.split('.')[1];
        if (!base64Payload) return null;
        const payload = JSON.parse(atob(base64Payload));
        return payload.exp ?? null;
    } catch {
        return null;
    }
}

/** 過期前幾分鐘顯示警告（毫秒） */
const WARNING_THRESHOLD_MS = 10 * 60 * 1000; // 10 分鐘
/** 檢查間隔（毫秒） */
const CHECK_INTERVAL_MS = 60 * 1000; // 1 分鐘

type WarningState = 'hidden' | 'warning' | 'expired';

export default function SessionExpiryWarning() {
    const { user, logout } = useUser();
    const location = useLocation();
    const isPublicPage = PUBLIC_PATHS.includes(location.pathname);
    const [state, setState] = useState<WarningState>('hidden');
    const [minutesLeft, setMinutesLeft] = useState(0);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const hasAutoLoggedOut = useRef(false);
    const isInitialCheck = useRef(true);
    const autoLogoutTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    const handleLogout = useCallback(() => {
        // 先清除 token，避免 redirect 後頁面 reload 時重新觸發過期警告
        localStorage.removeItem('access_token');
        localStorage.removeItem('user');
        logout();
        window.location.href = '/';
    }, [logout]);

    /**
     * 靜默登出：不顯示任何警告彈窗，直接清除資料並導回首頁。
     * 用於初始載入時發現 token 已過期的情境。
     */
    const silentLogout = useCallback(() => {
        // 清除 localStorage，避免下次 useEffect 重跑時又讀到舊 token
        localStorage.removeItem('access_token');
        localStorage.removeItem('user');
        logout();
        // 不用 window.location.href 避免閃爍，使用者會自然看到登入頁
    }, [logout]);

    /**
     * 延長登入：呼叫後端 refresh-token 端點取得新 token
     */
    const handleExtendSession = useCallback(async () => {
        setIsRefreshing(true);
        try {
            const token = localStorage.getItem('access_token');
            if (!token) {
                handleLogout();
                return;
            }

            const response = await fetch(`${API_BASE_URL}/api/auth/refresh-token`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json',
                },
            });

            if (!response.ok) {
                // Token 已完全過期或無效，無法刷新
                handleLogout();
                return;
            }

            const data = await response.json();
            localStorage.setItem('access_token', data.access_token);
            setState('hidden');
            hasAutoLoggedOut.current = false;
        } catch {
            // 網路錯誤等，先隱藏警告讓使用者繼續操作
            setState('hidden');
        } finally {
            setIsRefreshing(false);
        }
    }, [handleLogout]);

    useEffect(() => {
        if (!user) {
            setState('hidden');
            hasAutoLoggedOut.current = false;
            isInitialCheck.current = true;
            return;
        }

        // 公開頁面（登入/註冊）：不顯示 dialog，不動 localStorage
        // 使用者已在登入頁，不需要主動清除 token
        if (isPublicPage) {
            setState('hidden');
            return;
        }

        const checkExpiry = () => {
            const token = localStorage.getItem('access_token');
            if (!token) {
                if (isInitialCheck.current) {
                    // 初次檢查：沒有 token 代表舊 session，靜默登出不顯示警告
                    isInitialCheck.current = false;
                    silentLogout();
                    return;
                }
                if (!hasAutoLoggedOut.current) {
                    hasAutoLoggedOut.current = true;
                    handleLogout();
                }
                return;
            }

            const exp = parseJwtExp(token);
            if (!exp) return;

            const timeLeft = exp * 1000 - Date.now();

            if (timeLeft <= 0) {
                if (isInitialCheck.current) {
                    // 初次檢查就發現 token 已過期 → 靜默清除，不彈窗
                    isInitialCheck.current = false;
                    silentLogout();
                    return;
                }
                // 使用中過期 → 顯示過期提示
                setState('expired');
                if (!hasAutoLoggedOut.current) {
                    hasAutoLoggedOut.current = true;
                    autoLogoutTimerRef.current = setTimeout(handleLogout, 5000);
                }
                return;
            }

            // Token 仍有效，標記初始檢查完成
            isInitialCheck.current = false;

            if (timeLeft <= WARNING_THRESHOLD_MS) {
                // 即將過期 → 顯示警告（含延長按鈕）
                setState('warning');
                setMinutesLeft(Math.ceil(timeLeft / 60000));
            } else {
                setState('hidden');
            }
        };

        checkExpiry();
        const intervalId = setInterval(checkExpiry, CHECK_INTERVAL_MS);
        return () => {
            clearInterval(intervalId);
            if (autoLogoutTimerRef.current) {
                clearTimeout(autoLogoutTimerRef.current);
                autoLogoutTimerRef.current = null;
            }
        };
    }, [user, isPublicPage, handleLogout, silentLogout]);

    // 雙重保險：沒有登入的使用者絕不顯示警告
    if (state === 'hidden' || !user) return null;

    const isWarning = state === 'warning';

    return (
        <div
            style={{
                position: 'fixed',
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                backgroundColor: 'rgba(15, 23, 42, 0.6)',
                backdropFilter: 'blur(4px)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                zIndex: 99999,
                animation: 'fadeIn 0.3s ease',
            }}
        >
            <div
                style={{
                    backgroundColor: '#fff',
                    borderRadius: '20px',
                    padding: '36px 32px',
                    maxWidth: '400px',
                    width: '90%',
                    textAlign: 'center',
                    boxShadow: '0 25px 60px -15px rgba(0, 0, 0, 0.3)',
                    animation: 'slideUp 0.3s ease',
                    border: `1px solid ${isWarning ? '#E0E7FF' : '#FEE2E2'}`,
                }}
            >
                {/* Icon */}
                <div
                    style={{
                        width: '56px',
                        height: '56px',
                        borderRadius: '14px',
                        background: isWarning
                            ? 'linear-gradient(135deg, #EEF2FF, #DBEAFE)'
                            : 'linear-gradient(135deg, #FEF2F2, #FEE2E2)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        margin: '0 auto 20px',
                        fontSize: '24px',
                    }}
                >
                    {isWarning ? '⏳' : '🔒'}
                </div>

                {/* Title */}
                <h3
                    style={{
                        fontSize: '18px',
                        fontWeight: 700,
                        color: isWarning ? '#1E40AF' : '#991B1B',
                        marginBottom: '8px',
                    }}
                >
                    {isWarning ? '登入即將過期' : '登入已過期'}
                </h3>

                {/* Message */}
                <p
                    style={{
                        fontSize: '14px',
                        color: '#64748B',
                        lineHeight: 1.7,
                        marginBottom: '24px',
                    }}
                >
                    {isWarning
                        ? `您的登入將在 ${minutesLeft} 分鐘後過期，請儲存工作或點擊下方按鈕延長。`
                        : '您的登入憑證已過期，系統將自動登出。請重新登入以繼續使用。'}
                </p>

                {/* 延長登入按鈕 - 僅在 warning 狀態顯示 */}
                {isWarning && (
                    <button
                        onClick={handleExtendSession}
                        disabled={isRefreshing}
                        style={{
                            width: '100%',
                            padding: '12px 20px',
                            borderRadius: '12px',
                            border: 'none',
                            fontSize: '15px',
                            fontWeight: 600,
                            cursor: isRefreshing ? 'not-allowed' : 'pointer',
                            background: 'linear-gradient(135deg, #3B82F6, #2563EB)',
                            color: '#fff',
                            transition: 'all 0.2s ease',
                            marginBottom: '10px',
                            opacity: isRefreshing ? 0.7 : 1,
                            boxShadow: '0 4px 14px -3px rgba(37, 99, 235, 0.4)',
                        }}
                        onMouseEnter={(e) => {
                            if (!isRefreshing) {
                                e.currentTarget.style.transform = 'translateY(-1px)';
                                e.currentTarget.style.boxShadow = '0 6px 20px -3px rgba(37, 99, 235, 0.5)';
                            }
                        }}
                        onMouseLeave={(e) => {
                            e.currentTarget.style.transform = 'translateY(0)';
                            e.currentTarget.style.boxShadow = '0 4px 14px -3px rgba(37, 99, 235, 0.4)';
                        }}
                    >
                        {isRefreshing ? '延長中...' : '延長登入時間'}
                    </button>
                )}

                {/* 登出 / 重新登入按鈕 */}
                <button
                    onClick={handleLogout}
                    style={{
                        width: '100%',
                        padding: '11px 20px',
                        borderRadius: '12px',
                        border: isWarning ? '1.5px solid #E2E8F0' : 'none',
                        fontSize: '14px',
                        fontWeight: 600,
                        cursor: 'pointer',
                        backgroundColor: isWarning ? 'transparent' : '#DC2626',
                        color: isWarning ? '#64748B' : '#fff',
                        transition: 'all 0.2s ease',
                    }}
                    onMouseEnter={(e) => {
                        if (isWarning) {
                            e.currentTarget.style.backgroundColor = '#F8FAFC';
                            e.currentTarget.style.borderColor = '#CBD5E1';
                        } else {
                            e.currentTarget.style.opacity = '0.9';
                        }
                    }}
                    onMouseLeave={(e) => {
                        if (isWarning) {
                            e.currentTarget.style.backgroundColor = 'transparent';
                            e.currentTarget.style.borderColor = '#E2E8F0';
                        } else {
                            e.currentTarget.style.opacity = '1';
                        }
                    }}
                >
                    {isWarning ? '重新登入' : '返回登入頁'}
                </button>

                {isWarning && (
                    <button
                        onClick={() => setState('hidden')}
                        style={{
                            width: '100%',
                            padding: '8px',
                            marginTop: '6px',
                            border: 'none',
                            background: 'none',
                            fontSize: '13px',
                            cursor: 'pointer',
                            color: '#94A3B8',
                            transition: 'color 0.2s ease',
                        }}
                        onMouseEnter={(e) => {
                            e.currentTarget.style.color = '#64748B';
                        }}
                        onMouseLeave={(e) => {
                            e.currentTarget.style.color = '#94A3B8';
                        }}
                    >
                        稍後處理
                    </button>
                )}
            </div>

            <style>{`
                @keyframes fadeIn {
                    from { opacity: 0; }
                    to { opacity: 1; }
                }
                @keyframes slideUp {
                    from { opacity: 0; transform: translateY(20px); }
                    to { opacity: 1; transform: translateY(0); }
                }
            `}</style>
        </div>
    );
}

