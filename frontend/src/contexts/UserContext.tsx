// frontend/src/contexts/UserContext.tsx
import { createContext, useContext, useState, useEffect, useCallback, useRef, ReactNode } from 'react';
import { authClient } from '../services/authClient';
import { decodeJwtPayload } from '../utils/jwt';

interface User {
    user_id: number;
    email: string;
    full_name: string;
    role: string;
}

interface UserContextType {
    user: User | null;
    setUser: (user: User | null) => void;
    logout: () => void;
    /**
     * 登入時呼叫：寫入 localStorage + 更新 state。
     * 若偵測到瀏覽器已用「不同帳號」登入，會先跳確認對話框；
     * 使用者取消的話回傳 false，不寫入任何東西、呼叫端要中止導頁。
     */
    login: (userData: User, accessToken: string) => boolean;
    /** 以後端 /api/auth/me 為準重新同步目前使用者，回傳最新使用者或 null */
    refreshAuthenticatedUser: () => Promise<User | null>;
}

const USER_KEY = 'user';
const TOKEN_KEY = 'access_token';
const AUTH_CHANNEL_NAME = 'cookai-auth-sync';

const UserContext = createContext<UserContextType | undefined>(undefined);

function readCachedUser(): User | null {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    try {
        return JSON.parse(raw);
    } catch {
        return null;
    }
}

function clearAuthStorage() {
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem(TOKEN_KEY);
}

export function UserProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const channelRef = useRef<BroadcastChannel | null>(null);

    // 建立 BroadcastChannel（部分舊瀏覽器沒有這個 API，靜默略過即可）
    useEffect(() => {
        if (typeof BroadcastChannel === 'undefined') return;
        const channel = new BroadcastChannel(AUTH_CHANNEL_NAME);
        channelRef.current = channel;
        return () => channel.close();
    }, []);

    // 掛載時：從 localStorage 還原，並做 token/快取一致性檢查
    useEffect(() => {
        const token = localStorage.getItem(TOKEN_KEY);
        const cachedUser = readCachedUser();

        if (!token || !cachedUser) {
            return;
        }

        const payload = decodeJwtPayload(token);
        if (payload && String(payload.user_id) !== String(cachedUser.user_id)) {
            // token 跟快取的使用者對不上，代表這個瀏覽器的登入狀態已經漂移過
            // 前端解析只能拿來做 UI 判斷，不能取代後端驗證，這裡只做保守處理：清掉重登
            clearAuthStorage();
            return;
        }

        setUser(cachedUser);
    }, []);

    // 以後端為準重新同步（跨分頁通知後呼叫）
    const refreshAuthenticatedUser = useCallback(async (): Promise<User | null> => {
        const token = localStorage.getItem(TOKEN_KEY);
        if (!token) {
            setUser(null);
            return null;
        }
        try {
            const me = await authClient.getMe();
            localStorage.setItem(USER_KEY, JSON.stringify(me));
            setUser(me);
            return me;
        } catch {
            // 401 時 authClient 內部已經清空 storage 並導頁，這裡不用重複處理
            return null;
        }
    }, []);

    // 跨分頁同步管道 1：storage event（注意：只會通知「其他」分頁，不會通知自己）
    useEffect(() => {
        const handleStorage = (event: StorageEvent) => {
            if (event.key !== TOKEN_KEY && event.key !== USER_KEY) return;
            if (!localStorage.getItem(TOKEN_KEY)) {
                setUser(null);
            } else {
                refreshAuthenticatedUser();
            }
        };
        window.addEventListener('storage', handleStorage);
        return () => window.removeEventListener('storage', handleStorage);
    }, [refreshAuthenticatedUser]);

    // 跨分頁同步管道 2：BroadcastChannel（作為 storage event 的補強，通知更即時）
    useEffect(() => {
        const channel = channelRef.current;
        if (!channel) return;
        const handleMessage = (event: MessageEvent) => {
            if (event.data?.type !== 'AUTH_CHANGED') return;
            if (event.data.action === 'LOGOUT') {
                setUser(null);
            } else {
                refreshAuthenticatedUser();
            }
        };
        channel.addEventListener('message', handleMessage);
        return () => channel.removeEventListener('message', handleMessage);
    }, [refreshAuthenticatedUser]);

    const broadcast = useCallback((action: 'LOGIN' | 'LOGOUT' | 'SWITCH_ACCOUNT') => {
        channelRef.current?.postMessage({ type: 'AUTH_CHANGED', action });
    }, []);

    const login = useCallback((userData: User, accessToken: string): boolean => {
        const existingUser = readCachedUser();
        const isSwitchingAccount = !!existingUser && String(existingUser.user_id) !== String(userData.user_id);

        if (isSwitchingAccount) {
            // TODO: 之後可以換成專案既有的 Dialog / Modal 元件，這裡先用 window.confirm 讓邏輯先跑起來
            const confirmed = window.confirm(
                `這個瀏覽器目前已登入「${existingUser!.full_name}」，是否要切換成「${userData.full_name}」？\n\n注意：其他還開著舊帳號畫面的分頁會被登出。`
            );
            if (!confirmed) return false;
        }

        localStorage.setItem(USER_KEY, JSON.stringify(userData));
        localStorage.setItem(TOKEN_KEY, accessToken);
        setUser(userData);
        broadcast(isSwitchingAccount ? 'SWITCH_ACCOUNT' : 'LOGIN');
        return true;
    }, [broadcast]);

    const logout = useCallback(() => {
        clearAuthStorage();
        setUser(null);
        broadcast('LOGOUT');
    }, [broadcast]);

    return (
        <UserContext.Provider value={{ user, setUser, logout, login, refreshAuthenticatedUser }}>
            {children}
        </UserContext.Provider>
    );
}

export function useUser() {
    const context = useContext(UserContext);
    if (context === undefined) {
        throw new Error('useUser must be used within a UserProvider');
    }
    return context;
}
