/**
 * 应用配置常量。所有魔法数字集中在这里，避免散落在各个模块。
 */

// LLM / Embedding
export const ARK_BASE_URL =
  process.env.ARK_BASE_URL ?? "https://ark.cn-beijing.volces.com/api/v3";
export const ARK_API_KEY = process.env.ARK_API_KEY ?? "";
export const ARK_ENDPOINT_ID = process.env.ARK_ENDPOINT_ID ?? "";
export const ARK_EMBEDDING_ENDPOINT_ID =
  process.env.ARK_EMBEDDING_ENDPOINT_ID ?? "";

export const TAVILY_API_KEY = process.env.TAVILY_API_KEY ?? "";

// 目录
export const NOTES_DIR = "notes";
export const DATA_DIR = "data";
export const DB_PATH = `${DATA_DIR}/kb.sqlite`;

// Chunking（跟 Python 版对齐）
export const CHUNK_MAX_CHARS = 500;
export const CHUNK_OVERLAP = 50;

// Agent
export const MAX_ROUNDS = 8;

// Memory 压缩
export const MEMORY_TRIGGER_CHARS = 3000;
export const MEMORY_KEEP_RECENT_ROUNDS = 3;
