import vm from "node:vm";

export interface SandboxOptions {
  /** 同步代码的执行时间上限 */
  timeoutMs?: number;
  /** 包含 await 的整体时间上限 */
  totalTimeoutMs?: number;
}

/**
 * 执行模型写的 JS（Code Mode 的执行层）。
 *
 * 与 cloudflare/mcp 的 Dynamic Worker 沙箱对应，但 Node 下没有 isolate 级隔离：
 * vm 只能防误操作（拿不到 require/process/fs），不能当安全边界。
 * 生产多租户请把本文件换成 Cloudflare Workers Dynamic Worker / isolate 容器。
 */
export async function runUserCode(
  code: string,
  globals: Record<string, unknown>,
  options: SandboxOptions = {},
): Promise<unknown> {
  const syncTimeout = options.timeoutMs ?? 5_000;
  const totalTimeout = options.totalTimeoutMs ?? 15_000;

  const context = vm.createContext(
    {
      ...globals,
      console: { log: () => {}, info: () => {}, warn: () => {}, error: () => {} },
      setTimeout,
      clearTimeout,
      Promise,
      JSON,
    },
    {
      name: "tencentcloud-mcp-code",
      codeGeneration: { strings: false, wasm: false },
    },
  );

  const wrapped = `(async () => {\n${code}\n})()`;
  const script = new vm.Script(wrapped, { filename: "usercode.js" });

  let value: unknown;
  try {
    value = script.runInContext(context, { timeout: syncTimeout, displayErrors: false });
  } catch (error) {
    throw new Error(`代码执行失败：${(error as Error).message}`);
  }

  if (value && typeof (value as Promise<unknown>).then === "function") {
    value = await withTimeout(value as Promise<unknown>, totalTimeout);
  }
  return value;
}

async function withTimeout(promise: Promise<unknown>, ms: number): Promise<unknown> {
  let timer: NodeJS.Timeout | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(
      () => reject(new Error(`代码执行超时（>${ms}ms）：请减少请求次数或调小返回数据量。`)),
      ms,
    );
  });
  try {
    return await Promise.race([promise, timeout]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}
