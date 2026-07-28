// frontend/src/utils/jwt.ts

interface JwtPayload {
    user_id: number;
    email: string;
    role: string;
    exp: number;
}

/**
 * 解析 JWT payload，不驗證簽章。
 * 僅供前端 UI 判斷「這個 token 看起來是哪個使用者」，
 * 真正的身分驗證一律以後端 /api/auth/me 為準。
 */
export function decodeJwtPayload(token: string): JwtPayload | null {
    try {
        const base64Url = token.split('.')[1];
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        const json = decodeURIComponent(
            atob(base64)
                .split('')
                .map(c => '%' + c.charCodeAt(0).toString(16).padStart(2, '0'))
                .join('')
        );
        return JSON.parse(json);
    } catch {
        return null;
    }
}
