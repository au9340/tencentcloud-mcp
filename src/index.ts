import "dotenv/config";
import http from "node:http";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import {
  resolveCredentials,
  resolveEngine,
  UnauthorizedError,
} from "./core/auth.js";
import { buildServer } from "./mcp/server.js";

const PORT = Number(process.env.PORT ?? 8787);
const HOST = process.env.HOST ?? "0.0.0.0";
const MCP_PATH = process.env.MCP_PATH ?? "/mcp";
const MAX_BODY_BYTES = 1_048_576;

class HttpError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message?: string,
  ) {
    super(message ?? code);
    this.name = "HttpError";
  }
}

function sendJson(
  res: http.ServerResponse,
  status: number,
  payload: unknown,
  headers: Record<string, string> = {},
): void {
  const body = JSON.stringify(payload);
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
    ...headers,
  });
  res.end(body);
}

function rpcError(res: http.ServerResponse, status: number, code: number, message: string): void {
  sendJson(res, status, { jsonrpc: "2.0", error: { code, message }, id: null });
}

async function readBody(req: http.IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of req) {
    const buf = chunk as Buffer;
    size += buf.length;
    if (size > MAX_BODY_BYTES) throw new HttpError(413, "payload_too_large");
    chunks.push(buf);
  }
  if (!size) return undefined;
  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8")) as unknown;
  } catch {
    throw new HttpError(400, "invalid_json", "请求体不是合法 JSON");
  }
}

async function handleRequest(
  req: http.IncomingMessage,
  res: http.ServerResponse,
): Promise<void> {
  const url = new URL(req.url ?? "/", `http://${req.headers.host ?? "localhost"}`);

  if (url.pathname === "/healthz") {
    sendJson(res, 200, {
      ok: true,
      name: "tencentcloud-mcp",
      version: "0.1.0",
      engine: resolveEngine(url.searchParams.get("engine")),
      credentialMode: process.env.TENCENTCLOUD_SECRET_ID ? "server-env" : "per-request-bearer",
      endpoint: MCP_PATH,
    });
    return;
  }

  if (url.pathname !== MCP_PATH) {
    rpcError(res, 404, -32000, `未找到该路径，MCP 端点是 ${MCP_PATH}`);
    return;
  }

  // stateless 服务器只接 POST（Streamable HTTP）
  if (req.method !== "POST") {
    sendJson(
      res,
      405,
      { jsonrpc: "2.0", error: { code: -32000, message: "只支持 POST（无状态服务器）" }, id: null },
      { Allow: "POST" },
    );
    return;
  }

  let credentials;
  try {
    credentials = resolveCredentials(req.headers);
  } catch (error) {
    if (error instanceof UnauthorizedError) {
      sendJson(
        res,
        401,
        { jsonrpc: "2.0", error: { code: -32001, message: error.message }, id: null },
        { "WWW-Authenticate": 'Bearer realm="tencentcloud-mcp"' },
      );
      return;
    }
    throw error;
  }

  const body = await readBody(req);

  const server = buildServer({
    credentials,
    engine: resolveEngine(url.searchParams.get("engine")),
    truncateToolResult: url.searchParams.get("truncateToolResult") !== "false",
    defaultRegion: process.env.TENCENT_MCP_DEFAULT_REGION || undefined,
    maxRequests: Number(process.env.TENCENT_MCP_MAX_REQUESTS ?? 20),
    timeoutMs: Number(process.env.TENCENT_MCP_TIMEOUT_MS ?? 20_000),
    requireConfirm: process.env.TENCENT_MCP_REQUIRE_CONFIRM === "true",
  });

  const transport = new StreamableHTTPServerTransport({
    sessionIdGenerator: undefined,
    enableJsonResponse: true,
  });

  res.on("close", () => {
    void transport.close();
    void server.close();
  });

  await server.connect(transport);
  await transport.handleRequest(req, res, body);
}

const httpServer = http.createServer((req, res) => {
  const started = Date.now();
  handleRequest(req, res)
    .catch((error: unknown) => {
      const status = error instanceof HttpError ? error.status : 500;
      const message = error instanceof Error ? error.message : "internal error";
      if (!res.headersSent) rpcError(res, status, -32603, message);
      else res.end();
    })
    .finally(() => {
      console.error(`[${req.method ?? "?"}] ${req.url ?? "?"} ${Date.now() - started}ms`);
    });
});

httpServer.listen(PORT, HOST, () => {
  console.log(`tencentcloud-mcp listening on http://${HOST}:${PORT}${MCP_PATH}`);
  console.log(`engine=${process.env.TENCENT_MCP_ENGINE ?? "api"} healthz=/healthz`);
});

for (const signal of ["SIGINT", "SIGTERM"] as const) {
  process.on(signal, () => {
    console.log(`\n收到 ${signal}，正在关闭...`);
    httpServer.close(() => process.exit(0));
  });
}
