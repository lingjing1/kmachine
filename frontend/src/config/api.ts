// API 基礎 URL 配置
//  - VITE_API_URL = '' (空字串) → 走相對 /api（合併同 origin 部署，換網域免重 build）
//  - VITE_API_URL = 絕對網址     → 用該網址（本機開發指向 dev 後端，如 http://127.0.0.1:8002）
//  - VITE_API_URL 未設定          → 退回本機預設
// 用 ?? 而非 ||：空字串不是 nullish，會被保留（這正是相對路徑部署要的）

const API_BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export default API_BASE_URL;

