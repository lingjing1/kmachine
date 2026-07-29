// frontend/src/contexts/UserContext.tsx
import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
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
     * 登入時呼叫：寫入 sessionStorage + 更新 state。
     * 若這個分頁「自己」已經用不同帳號登入過（例如同一分頁先登出又登入別的帳號），
     * 會先跳確認對話框；使用者取消的話回傳 false，不寫入任何東西、呼叫端要中止導頁。
     */
    login: (userData: User, accessToken: string) => boolean;
    /** 以後端 /api/auth/me 為準重新同步目前使用者，回傳最新使用者或 null */
    refreshAuthenticatedUser: () => Promise<User | null>;
}

const USER_KEY = 'user';
const TOKEN_KEY = 'access_token';

const UserContext = createContext<UserContextType | undefined>(undefined);

function readCachedUser(): User | null {
    const raw = sessionStorage.getItem(USER_KEY);
    if (!raw) return null;
    try {
        return JSON.parse(raw);
    } catch {
        return null;
    }
}

function clearAuthStorage() {
    sessionStorage.removeItem(USER_KEY);
    sessionStorage.removeItem(TOKEN_KEY);
}

export function UserProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<User | null>(null);

    // 掛載時：從 sessionStorage 還原，並做 token/快取一致性檢查
    //
    // 登入狀態存在 sessionStorage 而非 localStorage：sessionStorage 天生
    // 每個分頁（browsing context）各自獨立，瀏覽器不會讓分頁之間共用，
    // 所以「別的分頁登入了別的帳號」這件事，這個分頁完全不會看到、也不需要監聽
    // storage event 或用 BroadcastChannel 跨分頁同步——結構上就不會互相汙染。
    // 代價（使用者已知並接受）：複製網址開新分頁不會自動帶入登入狀態、
    // 分頁關掉登入就消失，都要重新登入。
    useEffect(() => {
        const token = sessionStorage.getItem(TOKEN_KEY);
        const cachedUser = readCachedUser();

        if (!token || !cachedUser) {
            return;
        }

        const payload = decodeJwtPayload(token);
        if (payload && String(payload.user_id) !== String(cachedUser.user_id)) {
            // token 跟快取的使用者對不上（理論上不該發生，保留作為防禦性檢查）
            // 前端解析只能拿來做 UI 判斷，不能取代後端驗證，這裡只做保守處理：清掉重登
            clearAuthStorage();
            return;
        }

        setUser(cachedUser);
    }, []);

    // 以後端為準重新同步目前使用者（例如寫入操作前的保險檢查）
    const refreshAuthenticatedUser = useCallback(async (): Promise<User | null> => {
        const token = sessionStorage.getItem(TOKEN_KEY);
        if (!token) {
            setUser(null);
            return null;
        }
        try {
            const me = await authClient.getMe();
            sessionStorage.setItem(USER_KEY, JSON.stringify(me));
            setUser(me);
            return me;
        } catch {
            // 401 時 authClient 內部已經清空 storage 並導頁，這裡不用重複處理
            return null;
        }
    }, []);

    const login = useCallback((userData: User, accessToken: string): boolean => {
        const existingUser = readCachedUser();
        const isSwitchingAccount = !!existingUser && String(existingUser.user_id) !== String(userData.user_id);

        if (isSwitchingAccount) {
            // TODO: 之後可以換成專案既有的 Dialog / Modal 元件，這裡先用 window.confirm 讓邏輯先跑起來
            const confirmed = window.confirm(
                `這個分頁目前已登入「${existingUser!.full_name}」，是否要切換成「${userData.full_name}」？`
            );
            if (!confirmed) return false;
        }

        sessionStorage.setItem(USER_KEY, JSON.stringify(userData));
        sessionStorage.setItem(TOKEN_KEY, accessToken);
        setUser(userData);
        return true;
    }, []);

    const logout = useCallback(() => {
        clearAuthStorage();
        setUser(null);
    }, []);

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
