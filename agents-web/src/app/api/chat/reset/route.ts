/**
 * POST /api/chat/reset — 清空当前 agent 的对话记忆
 * GET  /api/memory     — 返回 memory 统计
 */
import { getAgent } from "@/lib/agent";

export const runtime = "nodejs";

export async function POST() {
  getAgent().clearMemory();
  return Response.json({ ok: true });
}
