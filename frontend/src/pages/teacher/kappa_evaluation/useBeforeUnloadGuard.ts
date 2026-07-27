/**
 * 當 `isDirty=true` 時，掛上 window.beforeunload 監聽器。
 * 使用者關閉分頁、重新整理、或導向外部網址時，瀏覽器會跳原生確認對話框。
 *
 * 注意：2016 年後 Chrome / Firefox / Safari 都已不允許自訂訊息文字，
 * 只能控制「要不要跳對話框」。提示內容由瀏覽器自動產生。
 *
 * 同一頁可多處呼叫此 hook（例如 Task A+B 的兩個 panel 各自判斷 dirty），
 * 多個 listener 疊加不衝突 —— 只要任一 isDirty=true，瀏覽器就會跳警告。
 */
import { useEffect } from 'react';

export function useBeforeUnloadGuard(isDirty: boolean) {
    useEffect(() => {
        if (!isDirty) return;
        const handler = (e: BeforeUnloadEvent) => {
            e.preventDefault();
            // Chrome 需要 returnValue 非空才會跳（即使文字被忽略）
            e.returnValue = '';
        };
        window.addEventListener('beforeunload', handler);
        return () => window.removeEventListener('beforeunload', handler);
    }, [isDirty]);
}
