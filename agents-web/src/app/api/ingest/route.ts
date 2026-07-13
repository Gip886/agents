/**
 * POST /api/ingest
 * 触发建库：读 notes/*.md → embedding → 写 SQLite。
 *
 * body: 可选 { save?: { filename, content }[] } —— 先保存这些新文件，再重建索引。
 */
import type { NextRequest } from "next/server";

import { rebuild, saveNote } from "@/lib/kb";

export const runtime = "nodejs";
export const maxDuration = 120;

export async function POST(req: NextRequest) {
  let body: { save?: { filename: string; content: string }[] } = {};
  try {
    const raw = await req.text();
    if (raw) body = JSON.parse(raw);
  } catch {
    return Response.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const savedNames: string[] = [];
  if (body.save && body.save.length > 0) {
    for (const f of body.save) {
      if (!f.filename.endsWith(".md")) {
        return Response.json(
          { error: `文件 ${f.filename} 不是 .md，跳过` },
          { status: 400 },
        );
      }
      saveNote(f.filename, f.content);
      savedNames.push(f.filename);
    }
  }

  try {
    const [nFiles, nChunks] = await rebuild();
    return Response.json({
      ok: true,
      saved: savedNames,
      files: nFiles,
      chunks: nChunks,
    });
  } catch (e) {
    return Response.json({ error: (e as Error).message }, { status: 500 });
  }
}
