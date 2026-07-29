// frontend/src/services/authClient.ts
import API_BASE_URL from '../config/api';

/**
 * AuthClient - 統一的 API 請求工具，自動處理 JWT 認證
 * 
 * 功能：
 * - 自動從 sessionStorage 讀取 token（每個分頁獨立登入狀態）
 * - 自動注入 Authorization header
 * - 處理 401 錯誤（token 過期）
 * - 提供 GET, POST, PUT, DELETE 方法
 */
class AuthClient {
    /**
     * 獲取 Authorization header
     */
    private getAuthHeader(): HeadersInit {
        const token = sessionStorage.getItem('access_token');
        if (!token) {
            return {};
        }
        return {
            'Authorization': `Bearer ${token}`
        };
    }

    /**
     * 通用請求方法
     */
    async request<T>(
        endpoint: string,
        options: RequestInit & { responseType?: 'json' | 'blob' } = {}
    ): Promise<T> {
        const url = `${API_BASE_URL}${endpoint}`;
        const { responseType = 'json', ...fetchOptions } = options;

        const headers = {
            'Content-Type': 'application/json',
            ...this.getAuthHeader(),
            ...fetchOptions.headers,
        };

        try {
            const response = await fetch(url, {
                ...fetchOptions,
                headers,
            });

            // ✅ 處理 401 - Token 過期或無效
            if (response.status === 401 || response.status === 403) {
                this.handleUnauthorized();
                throw new Error('Authentication failed');
            }

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ detail: 'Request failed' }));
                const error = new Error(errorData.detail || 'Request failed') as any;
                error.status = response.status;
                error.response = { status: response.status, data: errorData };
                throw error;
            }

            // 處理空響應（204 No Content）
            if (response.status === 204) {
                return {} as T;
            }

            if (responseType === 'blob') {
                return await response.blob() as unknown as T;
            }

            return await response.json();
        } catch (error) {
            // 如果是我們拋出的錯誤，直接傳遞
            if (error instanceof Error) {
                throw error;
            }
            // 網絡錯誤等其他錯誤
            throw new Error('Network error or request failed');
        }
    }

    /**
     * 處理未授權錯誤
     */
    private handleUnauthorized() {
        // 清除 token 和用戶資訊
        sessionStorage.removeItem('access_token');
        sessionStorage.removeItem('user');

        // 導向首頁（會觸發登入）
        window.location.href = '/';
    }

    /**
     * GET 請求
     */
    async get<T>(
        endpoint: string,
        queryParams?: Record<string, any>,
        options: { responseType?: 'json' | 'blob' } = {}
    ): Promise<T> {
        let url = endpoint;
        const { responseType = 'json' } = options;

        if (queryParams) {
            const params = new URLSearchParams();
            Object.entries(queryParams).forEach(([key, value]) => {
                if (value !== undefined && value !== null) {
                    params.append(key, String(value));
                }
            });
            const queryString = params.toString();
            if (queryString) {
                url += `?${queryString}`;
            }
        }

        return this.request<T>(url, { method: 'GET', responseType });
    }

    /**
     * POST 請求
     */
    async post<T>(endpoint: string, data?: any): Promise<T> {
        return this.request<T>(endpoint, {
            method: 'POST',
            body: data ? JSON.stringify(data) : undefined,
        });
    }

    /**
     * PUT 請求
     */
    async put<T>(endpoint: string, data: any): Promise<T> {
        return this.request<T>(endpoint, {
            method: 'PUT',
            body: JSON.stringify(data),
        });
    }

    /**
     * DELETE 請求
     */
    async delete<T>(endpoint: string): Promise<T> {
        return this.request<T>(endpoint, { method: 'DELETE' });
    }

    /**
     * POST with FormData (for file uploads)
     */
    async postFormData<T>(endpoint: string, formData: FormData): Promise<T> {
        const url = `${API_BASE_URL}${endpoint}`;

        // FormData 不需要設置 Content-Type，瀏覽器會自動設置
        const headers = {
            ...this.getAuthHeader(),
        };

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers,
                body: formData,
            });

            if (response.status === 401 || response.status === 403) {
                this.handleUnauthorized();
                throw new Error('Authentication failed');
            }

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ detail: 'Request failed' }));
                const error = new Error(errorData.detail || 'Request failed') as any;
                error.status = response.status;
                error.response = { status: response.status, data: errorData };
                throw error;
            }

            if (response.status === 204) {
                return {} as T;
            }

            return await response.json();
        } catch (error) {
            if (error instanceof Error) {
                throw error;
            }
            throw new Error('Network error or request failed');
        }
    }

    /**
     * 取得目前 token 對應的使用者資訊（後端為準，不是 sessionStorage 快取）
     */
    async getMe(): Promise<{ user_id: number; email: string; full_name: string; role: string }> {
        return this.get('/api/auth/me');
    }
}

// Export singleton instance
export const authClient = new AuthClient();
export default authClient;
