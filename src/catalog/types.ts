export interface ActionDoc {
  /** 一句话说明，会直接进模型上下文，所以写短 */
  summary: string;
  /** 关键参数：参数名 -> 说明（不必全量，只记常用的） */
  params?: Record<string, string>;
  /** 是否需要 Region（默认 true） */
  requiresRegion?: boolean;
  /** 写/删/重启类高危操作，供 confirm 安全闸使用 */
  dangerous?: boolean;
}

export interface ServiceDoc {
  /** API 版本，例如 2017-03-12 */
  version: string;
  /** 产品中文名 */
  product: string;
  /** 产品 API 文档首页 */
  docUrl: string;
  actions: Record<string, ActionDoc>;
}

export type Catalog = Record<string, ServiceDoc>;

/** 扁平化后的条目，给 search / docs 工具用 */
export interface ActionEntry {
  service: string;
  version: string;
  product: string;
  action: string;
  summary: string;
  requiresRegion: boolean;
  dangerous: boolean;
  params: Record<string, string>;
  docUrl: string;
}
