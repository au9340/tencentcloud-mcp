import { cam } from "./services/cam.js";
import { cbs } from "./services/cbs.js";
import { clb } from "./services/clb.js";
import { cvm } from "./services/cvm.js";
import { dnspod } from "./services/dnspod.js";
import { lighthouse } from "./services/lighthouse.js";
import { scf } from "./services/scf.js";
import { sts } from "./services/sts.js";
import { tat } from "./services/tat.js";
import { vpc } from "./services/vpc.js";
import type { ActionEntry, Catalog } from "./types.js";

/**
 * Action 目录：相当于 cloudflare/mcp 里那份 OpenAPI spec 的“瘦身版”。
 * 真正的 spec 是 2M tokens 级别，这里只留“产品指路牌”：服务名 + 版本 + Action 名 + 常用参数。
 * 缺产品就补一个 src/catalog/services/<service>.ts，不用改任何其他代码。
 */
export const catalog: Catalog = {
  cam,
  cbs,
  clb,
  cvm,
  dnspod,
  lighthouse,
  scf,
  sts,
  tat,
  vpc,
};

function flatten(input: Catalog): ActionEntry[] {
  const entries: ActionEntry[] = [];
  for (const [service, doc] of Object.entries(input)) {
    for (const [action, meta] of Object.entries(doc.actions)) {
      entries.push({
        service,
        version: doc.version,
        product: doc.product,
        action,
        summary: meta.summary,
        requiresRegion: meta.requiresRegion !== false,
        dangerous: meta.dangerous === true,
        params: meta.params ?? {},
        docUrl: doc.docUrl,
      });
    }
  }
  return entries;
}

export const actionList: ActionEntry[] = flatten(catalog);

export function resolveVersion(service: string): string | undefined {
  return catalog[service.trim().toLowerCase()]?.version;
}

/** 关键词打分搜索，给 docs 工具与沙箱里的 searchActions 用 */
export function searchActions(query: string, limit = 20): ActionEntry[] {
  const terms = query
    .toLowerCase()
    .split(/[\s,;/]+/)
    .filter(Boolean);
  if (!terms.length) return actionList.slice(0, limit);

  const scored = actionList.map((entry) => {
    const haystack = [
      entry.service,
      entry.product,
      entry.action,
      entry.summary,
      ...Object.keys(entry.params),
      ...Object.values(entry.params),
    ]
      .join(" ")
      .toLowerCase();
    let score = 0;
    for (const term of terms) {
      if (!haystack.includes(term)) continue;
      score += 1;
      if (entry.action.toLowerCase().includes(term)) score += 2;
      if (entry.service === term) score += 1;
    }
    return { entry, score };
  });

  return scored
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
    .map((item) => item.entry);
}
