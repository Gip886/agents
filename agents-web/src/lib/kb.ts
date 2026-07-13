/**
 * 知识库访问层：SQLite + 手写 cosine similarity。
 *
 * schema:
 *   chunks(id TEXT PK, file TEXT, chunk_idx INT, text TEXT, embedding BLOB)
 *     embedding 是 Float32Array 的字节序列，取回时 view 出来
 *
 * 对比 Python 版：
 *   - 用 SQLite 替代 ChromaDB —— 零外部服务、可上 serverless、chunks 少时性能够
 *   - 手写 cosine —— 展示"向量搜索是什么"，学习价值更高
 *   - notes 全文和 frontmatter 仍读文件系统（read_full_note、read_meta）
 */
import fs from "node:fs";
import path from "node:path";
import Database from "better-sqlite3";

import { DATA_DIR, DB_PATH, NOTES_DIR } from "./config";
import { splitText } from "./chunk";
import { embedOne, embedTexts } from "./embedding";
import { dump as fmDump, FrontmatterMeta, parse as fmParse } from "./frontmatter";

export type SearchHit = {
  text: string;
  file: string;
  chunk_idx: number;
  similarity: number;
};

// ============================================================
// SQLite 客户端
// ============================================================

let _db: Database.Database | null = null;

function getDb(): Database.Database {
  if (_db) return _db;
  fs.mkdirSync(DATA_DIR, { recursive: true });
  _db = new Database(DB_PATH);
  _db.pragma("journal_mode = WAL");
  _db.exec(`
    CREATE TABLE IF NOT EXISTS chunks (
      id TEXT PRIMARY KEY,
      file TEXT NOT NULL,
      chunk_idx INTEGER NOT NULL,
      text TEXT NOT NULL,
      embedding BLOB NOT NULL,
      tags TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_chunks_file ON chunks(file);
  `);
  return _db;
}

function embeddingToBlob(v: number[]): Buffer {
  const arr = new Float32Array(v);
  return Buffer.from(arr.buffer);
}

function blobToEmbedding(buf: Buffer): Float32Array {
  return new Float32Array(
    buf.buffer,
    buf.byteOffset,
    buf.byteLength / Float32Array.BYTES_PER_ELEMENT,
  );
}

// ============================================================
// Cosine similarity —— 手写就一行数学
// ============================================================

/**
 * 余弦相似度。两个向量维度必须一致，否则 undefined 行为。
 * 结果在 [-1, 1] 之间，越大越相似。
 */
function cosineSimilarity(a: ArrayLike<number>, b: ArrayLike<number>): number {
  let dot = 0;
  let na = 0;
  let nb = 0;
  const len = a.length;
  for (let i = 0; i < len; i++) {
    dot += a[i] * b[i];
    na += a[i] * a[i];
    nb += b[i] * b[i];
  }
  const denom = Math.sqrt(na) * Math.sqrt(nb);
  return denom === 0 ? 0 : dot / denom;
}

// ============================================================
// 建库
// ============================================================

/**
 * 清空并重建 chunks 表：读 notes/*.md → 剥 frontmatter → 切分 → embedding → 入库。
 * 返回 [文件数, chunk 数]。
 */
export async function rebuild(): Promise<[number, number]> {
  const db = getDb();

  // 收集 .md
  if (!fs.existsSync(NOTES_DIR)) {
    throw new Error(`notes/ 目录不存在：${NOTES_DIR}`);
  }
  const mdFiles = fs
    .readdirSync(NOTES_DIR)
    .filter((n) => n.endsWith(".md"))
    .sort();
  if (mdFiles.length === 0) {
    throw new Error(`${NOTES_DIR}/ 下没有 .md 文件`);
  }

  // 准备 chunks
  type Row = { id: string; file: string; chunk_idx: number; text: string; tags: string | null };
  const rows: Row[] = [];
  const allTexts: string[] = [];

  for (const filename of mdFiles) {
    const raw = fs.readFileSync(path.join(NOTES_DIR, filename), "utf-8");
    const [meta, text] = fmParse(raw);
    const chunks = splitText(text);
    const tagStr = Array.isArray(meta.tags) ? meta.tags.join(",") : null;

    for (let i = 0; i < chunks.length; i++) {
      rows.push({
        id: `${filename}#${i}`,
        file: filename,
        chunk_idx: i,
        text: chunks[i],
        tags: tagStr,
      });
      allTexts.push(chunks[i]);
    }
  }

  // Embedding（批量调 API；打印进度）
  const batchSize = 8;
  const allEmbeddings: number[][] = [];
  for (let i = 0; i < allTexts.length; i += batchSize) {
    const batch = allTexts.slice(i, i + batchSize);
    const vecs = await embedTexts(batch);
    allEmbeddings.push(...vecs);
  }

  // 写库：整个动作放事务里，速度快 + 原子性
  const write = db.transaction(() => {
    db.exec("DELETE FROM chunks");
    const insert = db.prepare(
      "INSERT INTO chunks (id, file, chunk_idx, text, embedding, tags) VALUES (?, ?, ?, ?, ?, ?)",
    );
    for (let i = 0; i < rows.length; i++) {
      const r = rows[i];
      insert.run(r.id, r.file, r.chunk_idx, r.text, embeddingToBlob(allEmbeddings[i]), r.tags);
    }
  });
  write();

  return [mdFiles.length, rows.length];
}

// ============================================================
// 查询
// ============================================================

/**
 * 语义检索。加载所有 chunk 到内存做 cosine（chunks 少时够用；上万级要换 sqlite-vec 或 pgvector）。
 */
export async function search(query: string, topK = 3): Promise<SearchHit[]> {
  const db = getDb();
  const qVec = new Float32Array(await embedOne(query));

  const rows = db.prepare("SELECT file, chunk_idx, text, embedding FROM chunks").all() as {
    file: string;
    chunk_idx: number;
    text: string;
    embedding: Buffer;
  }[];

  const scored = rows.map((r) => ({
    text: r.text,
    file: r.file,
    chunk_idx: r.chunk_idx,
    similarity: cosineSimilarity(qVec, blobToEmbedding(r.embedding)),
  }));
  scored.sort((a, b) => b.similarity - a.similarity);
  return scored.slice(0, topK).map((h) => ({
    ...h,
    similarity: Math.round(h.similarity * 1000) / 1000,
  }));
}

export function countChunks(): number {
  const db = getDb();
  const row = db.prepare("SELECT COUNT(*) as c FROM chunks").get() as { c: number };
  return row.c;
}

// ============================================================
// 文件访问（笔记全文 / frontmatter 元数据）
// ============================================================

const MAX_FULL_NOTE_CHARS = 8000;

export function listNotes(): string[] {
  if (!fs.existsSync(NOTES_DIR)) return [];
  return fs
    .readdirSync(NOTES_DIR)
    .filter((n) => n.endsWith(".md"))
    .sort();
}

export function readFullNote(filename: string): string {
  const p = path.join(NOTES_DIR, filename);
  if (!fs.existsSync(p)) throw new Error(`笔记不存在：${filename}`);
  const raw = fs.readFileSync(p, "utf-8");
  const [, body] = fmParse(raw);
  if (body.length > MAX_FULL_NOTE_CHARS) {
    return (
      body.slice(0, MAX_FULL_NOTE_CHARS) +
      `\n\n[...原文过长已截断，总长 ${body.length} 字符，仅展示前 ${MAX_FULL_NOTE_CHARS} 字符]`
    );
  }
  return body;
}

export function readMeta(filename: string): FrontmatterMeta {
  const p = path.join(NOTES_DIR, filename);
  if (!fs.existsSync(p)) throw new Error(`笔记不存在：${filename}`);
  const raw = fs.readFileSync(p, "utf-8");
  return fmParse(raw)[0];
}

/**
 * 更新笔记 frontmatter：合并覆盖，list 类型做去重合并（tags 场景）。
 * 返回合并后完整 meta。
 */
export function updateMeta(filename: string, updates: FrontmatterMeta): FrontmatterMeta {
  const p = path.join(NOTES_DIR, filename);
  if (!fs.existsSync(p)) throw new Error(`笔记不存在：${filename}`);

  const raw = fs.readFileSync(p, "utf-8");
  const [meta, body] = fmParse(raw);

  for (const [k, v] of Object.entries(updates)) {
    if (Array.isArray(v) && Array.isArray(meta[k])) {
      const seen = new Set(meta[k]);
      const merged = [...(meta[k] as string[])];
      for (const item of v) {
        if (!seen.has(item)) {
          merged.push(item);
          seen.add(item);
        }
      }
      meta[k] = merged;
    } else {
      meta[k] = v;
    }
  }

  fs.writeFileSync(p, fmDump(meta, body), "utf-8");
  return meta;
}

/** 保存一个新上传的笔记文件到 notes/。返回文件名。 */
export function saveNote(filename: string, content: string): string {
  fs.mkdirSync(NOTES_DIR, { recursive: true });
  fs.writeFileSync(path.join(NOTES_DIR, filename), content, "utf-8");
  return filename;
}
