/**
 * 文本切分 —— 段落切分 + 长段落滑窗（对齐 day7/knowledge_base.py 的 split_text）
 */
import { CHUNK_MAX_CHARS, CHUNK_OVERLAP } from "./config";

export function splitText(
  text: string,
  maxChars = CHUNK_MAX_CHARS,
  overlap = CHUNK_OVERLAP,
): string[] {
  const paragraphs = text
    .split("\n\n")
    .map((p) => p.trim())
    .filter(Boolean);

  const chunks: string[] = [];
  for (const para of paragraphs) {
    if (para.length <= maxChars) {
      chunks.push(para);
      continue;
    }
    // 长段落滑窗切
    let start = 0;
    while (start < para.length) {
      const end = start + maxChars;
      chunks.push(para.slice(start, end));
      if (end >= para.length) break;
      start = end - overlap;
    }
  }
  return chunks;
}
