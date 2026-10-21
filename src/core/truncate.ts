const CHARS_PER_TOKEN = 4;

export interface TruncateOptions {
  /** 上限，按 1 token ≈ 4 字符估算 */
  maxTokens?: number;
  enabled?: boolean;
}

/**
 * 与 cloudflare/mcp 一致：单个工具结果默认截断在 ~6000 tokens，
 * 超长部分用 --- TRUNCATED --- 标记；可用 ?truncateToolResult=false 关掉。
 */
export function truncateText(text: string, options: TruncateOptions = {}): string {
  const enabled = options.enabled ?? true;
  if (!enabled) return text;

  const maxChars = (options.maxTokens ?? 6_000) * CHARS_PER_TOKEN;
  if (text.length <= maxChars) return text;

  return (
    text.slice(0, maxChars) +
    `\n--- TRUNCATED ---\n（原始 ${text.length} 字符，已截断到 ${maxChars} 字符；` +
    `如需完整结果，请在代码里只返回需要的字段，或用 ?truncateToolResult=false 关闭截断）`
  );
}

/** 安全地 JSON 序列化（处理 undefined / BigInt / 循环引用） */
export function stringify(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === undefined) return "undefined（代码没有返回值，记得 return）";

  const seen = new WeakSet<object>();
  try {
    return JSON.stringify(
      value,
      (_key, val: unknown) => {
        if (typeof val === "bigint") return val.toString();
        if (typeof val === "object" && val !== null) {
          if (seen.has(val)) return "[Circular]";
          seen.add(val);
        }
        return val;
      },
      2,
    );
  } catch (error) {
    return `结果无法序列化为 JSON：${(error as Error).message}`;
  }
}
