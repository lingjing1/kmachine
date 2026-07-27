// `crypto.randomUUID()` 只在 secure context (HTTPS / localhost) 可用。
// 部署在純 HTTP 環境時呼叫會丟 TypeError，這個 helper 提供三層 fallback：
//   1. crypto.randomUUID — 原生最快
//   2. crypto.getRandomValues — HTTP 環境也能用，自己組 UUID v4
//   3. Math.random — 最後保險（非 cryptographic，但 session id 場景夠用）
// 三層輸出格式都是標準 UUID v4，後端無感。

export function safeRandomUUID(): string {
    const g: any = typeof globalThis !== 'undefined' ? globalThis : {};

    if (g.crypto?.randomUUID) {
        return g.crypto.randomUUID();
    }

    if (g.crypto?.getRandomValues) {
        const bytes = new Uint8Array(16);
        g.crypto.getRandomValues(bytes);
        bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
        bytes[8] = (bytes[8] & 0x3f) | 0x80; // variant 10
        return formatUuid(bytes);
    }

    const bytes = new Uint8Array(16);
    for (let i = 0; i < 16; i++) bytes[i] = Math.floor(Math.random() * 256);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    return formatUuid(bytes);
}

function formatUuid(b: Uint8Array): string {
    const h = Array.from(b, x => x.toString(16).padStart(2, '0'));
    return `${h.slice(0, 4).join('')}-${h.slice(4, 6).join('')}-${h.slice(6, 8).join('')}-${h.slice(8, 10).join('')}-${h.slice(10, 16).join('')}`;
}
