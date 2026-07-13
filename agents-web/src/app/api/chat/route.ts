/**
 * POST /api/chat
 * body: { message: string }
 * 返回 SSE 流：每个事件形如 `data: {...JSON}\n\n`
 *
 * 前端约定：
 *   - answer_delta 拼接后即为最终答案
 *   - tool_call_start / tool_call_result 展示工具调用轨迹
 *   - turn_done 带完整 TurnResult
 */
import type { NextRequest } from "next/server";

import { getAgent } from "@/lib/agent";

export const runtime = "nodejs"; // 需要 fs / better-sqlite3
export const dynamic = "force-dynamic";
export const maxDuration = 60;

export async function POST(req: NextRequest) {
  let body: { message?: string };
  try {
    body = await req.json();
  } catch {
    return new Response("Invalid JSON", { status: 400 });
  }
  const message = body.message?.trim();
  if (!message) return new Response("message 不能为空", { status: 400 });

  const agent = getAgent();
  const encoder = new TextEncoder();

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const send = (obj: unknown) => {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(obj)}\n\n`));
      };
      try {
        for await (const event of agent.runTurnStream(message)) {
          send(event);
        }
        // 结束信号（EventSource 语义友好）
        controller.enqueue(encoder.encode(`event: end\ndata: {}\n\n`));
      } catch (e) {
        send({ type: "error", message: (e as Error).message });
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}

// 便于前端探活
export async function GET() {
  return new Response(JSON.stringify({ ok: true }), {
    headers: { "Content-Type": "application/json" },
  });
}
