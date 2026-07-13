/**
 * GET /api/notes
 * 返回：{ notes: [{ name, tags, summary }], chunk_count }
 */
import { countChunks, listNotes, readMeta } from "@/lib/kb";

export const runtime = "nodejs";

export async function GET() {
  const names = listNotes();
  const notes = names.map((name) => {
    let tags: string[] = [];
    let summary = "";
    try {
      const meta = readMeta(name);
      if (Array.isArray(meta.tags)) tags = meta.tags;
      if (typeof meta.summary === "string") summary = meta.summary;
    } catch {
      // 忽略单个失败
    }
    return { name, tags, summary };
  });
  let chunks = 0;
  try {
    chunks = countChunks();
  } catch {
    // 库还没建
  }
  return Response.json({ notes, chunk_count: chunks });
}
