# AGENTS.md

给在本仓库里干活的 AI agent 的少量硬约束。

## 不改的东西

- 工具面固定为 4 个：`search` / `execute` / `docs` / `whoami`。不要为了“方便”新增 `list_instances` 之类的专用工具——那正是 Code Mode 要避免的方向。
- 新增能力优先加在 `src/core/`（能力）或 `src/catalog/`（知识），不要加在工具层。

## 改代码时注意

- 相对 import 必须带 `.js` 后缀（NodeNext ESM + tsc 输出到 dist）。
- `Credential` / `ResolvedRequest` 等类型定义在 `src/core/types.ts`，不要重复定义。
- 任何新增的网络调用都要走 `src/core/requester.ts`，以继承版本解析、region 校验、confirm 安全闸和限流。
- 输出给模型的内容必须经过 `truncateText`，否则会撑爆上下文。

## 提交前

```bash
npm run typecheck && npm test
```
