/**
 * 极简 YAML frontmatter 解析器（Python 版 frontmatter.py 的 TS 对应）
 *
 * 支持格式：
 *     ---
 *     tags: [go, error-handling]
 *     summary: Go 用返回值传错误
 *     ---
 *     # 正文
 *
 * 不引 gray-matter/js-yaml —— 只支持 3 种值：字符串、字符串列表、简单标量。
 */

const FRONTMATTER_RE = /^---\s*\n([\s\S]*?)\n---\s*\n?/;

export type FrontmatterMeta = Record<string, string | string[]>;

/**
 * 从文本头部解析 frontmatter，返回 [meta, bodyWithoutFrontmatter]。
 * 没有 frontmatter 时 meta 为空对象、body 原样返回。
 */
export function parse(text: string): [FrontmatterMeta, string] {
  const m = text.match(FRONTMATTER_RE);
  if (!m) return [{}, text];

  const fmText = m[1];
  const body = text.slice(m[0].length);
  const meta: FrontmatterMeta = {};

  for (const rawLine of fmText.split("\n")) {
    const line = rawLine.trimEnd();
    if (!line) continue;

    // 缩进行（多行值延续）不支持；只处理 "key: value" 形式
    if (!line.includes(":") || line.startsWith(" ")) continue;

    const idx = line.indexOf(":");
    const key = line.slice(0, idx).trim();
    let value = line.slice(idx + 1).trim();

    if (value.startsWith("[") && value.endsWith("]")) {
      // 列表
      const items = value
        .slice(1, -1)
        .split(",")
        .map((x) => x.trim().replace(/^['"]|['"]$/g, ""))
        .filter(Boolean);
      meta[key] = items;
    } else if (value === "") {
      meta[key] = "";
    } else {
      // 剥单/双引号
      if (
        (value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'"))
      ) {
        value = value.slice(1, -1);
      }
      meta[key] = value;
    }
  }

  return [meta, body];
}

/**
 * 把 meta + body 拼回带 frontmatter 的文本。空 meta 时不加 frontmatter。
 */
export function dump(meta: FrontmatterMeta, body: string): string {
  if (Object.keys(meta).length === 0) return body;

  const lines = ["---"];
  for (const [key, value] of Object.entries(meta)) {
    if (Array.isArray(value)) {
      lines.push(`${key}: [${value.join(", ")}]`);
    } else if (typeof value === "string" && /[\n:#]/.test(value)) {
      // 含特殊字符加引号
      const escaped = value.replace(/"/g, '\\"').replace(/\n/g, " ");
      lines.push(`${key}: "${escaped}"`);
    } else {
      lines.push(`${key}: ${value}`);
    }
  }
  lines.push("---");
  lines.push("");

  return lines.join("\n") + (body.startsWith("\n") ? body : body);
}

/** 只要 body 部分 */
export function strip(text: string): string {
  return parse(text)[1];
}
