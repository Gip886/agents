"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { TurnEvent, TurnResult } from "@/lib/agent";
import { consumeSSE } from "@/lib/sse-client";

type NotesInfo = {
  notes: { name: string; tags: string[]; summary: string }[];
  chunk_count: number;
};

type MemoryStats = {
  n_messages: number;
  chars: number;
  trigger_chars: number;
};

type ChatMsg = {
  id: number;
  role: "user" | "assistant";
  content: string;
  turn?: TurnResult;
};

type ActiveTurn = {
  answer: string;
  events: TurnEvent[]; // 保留完整事件流用于渲染 tool 卡片
  activeToolNames: string[];
};

export default function Page() {
  // —— 全局状态 ——
  const [history, setHistory] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [active, setActive] = useState<ActiveTurn | null>(null);
  const [notesInfo, setNotesInfo] = useState<NotesInfo>({ notes: [], chunk_count: 0 });
  const [memStats, setMemStats] = useState<MemoryStats>({
    n_messages: 1,
    chars: 0,
    trigger_chars: 3000,
  });
  const [notice, setNotice] = useState<string | null>(null);
  const [ingesting, setIngesting] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // —— 拉取笔记 / 记忆状态 ——
  const refreshSidebar = useCallback(async () => {
    try {
      const [ni, ms] = await Promise.all([
        fetch("/api/notes").then((r) => r.json() as Promise<NotesInfo>),
        fetch("/api/memory").then((r) => r.json() as Promise<MemoryStats>),
      ]);
      setNotesInfo(ni);
      setMemStats(ms);
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => {
    refreshSidebar();
  }, [refreshSidebar]);

  // —— 自动滚动到底部 ——
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [history, active]);

  // —— 提交消息 ——
  const submit = async () => {
    const text = input.trim();
    if (!text || streaming) return;
    const userMsgId = Date.now();
    setInput("");
    setHistory((h) => [...h, { id: userMsgId, role: "user", content: text }]);
    setActive({ answer: "", events: [], activeToolNames: [] });
    setStreaming(true);

    let finalTurn: TurnResult | null = null;
    try {
      await consumeSSE<TurnEvent>(
        "/api/chat",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text }),
        },
        (evt) => {
          setActive((prev) => {
            if (!prev) return prev;
            const next: ActiveTurn = { ...prev, events: [...prev.events, evt] };
            if (evt.type === "answer_delta") {
              next.answer = prev.answer + evt.text;
            } else if (evt.type === "tool_call_start") {
              next.activeToolNames = [...prev.activeToolNames, evt.name];
            } else if (evt.type === "tool_call_result") {
              next.activeToolNames = prev.activeToolNames.filter((n) => n !== evt.name);
            } else if (evt.type === "turn_done") {
              finalTurn = evt.result;
            }
            return next;
          });
        },
      );
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setActive((prev) =>
        prev
          ? { ...prev, answer: prev.answer + `\n\n❌ 出错：${msg}` }
          : prev,
      );
    }

    setHistory((h) => [
      ...h,
      {
        id: userMsgId + 1,
        role: "assistant",
        content: finalTurn?.answer ?? "(无回复)",
        turn: finalTurn ?? undefined,
      },
    ]);
    setActive(null);
    setStreaming(false);
    refreshSidebar();
  };

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  const clearHistory = async () => {
    await fetch("/api/chat/reset", { method: "POST" });
    setHistory([]);
    refreshSidebar();
    setNotice("对话历史已清空");
  };

  // —— 上传 + 重建 ——
  const uploadAndIngest = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setIngesting(true);
    setNotice("正在上传 + 重建索引…");
    try {
      const filesPayload = await Promise.all(
        Array.from(files).map(async (f) => ({
          filename: f.name,
          content: await f.text(),
        })),
      );
      const resp = await fetch("/api/ingest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ save: filesPayload }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || "建库失败");
      setNotice(
        `✅ 已保存 ${data.saved.length} 个文件，索引重建为 ${data.files} 文件 / ${data.chunks} chunk`,
      );
      refreshSidebar();
    } catch (e) {
      setNotice(`❌ ${(e as Error).message}`);
    } finally {
      setIngesting(false);
    }
  };

  const rebuildOnly = async () => {
    setIngesting(true);
    setNotice("正在重建索引…");
    try {
      const resp = await fetch("/api/ingest", { method: "POST" });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || "建库失败");
      setNotice(`✅ 索引重建为 ${data.files} 文件 / ${data.chunks} chunk`);
      refreshSidebar();
    } catch (e) {
      setNotice(`❌ ${(e as Error).message}`);
    } finally {
      setIngesting(false);
    }
  };

  // —— 渲染 ——
  const memRatio = Math.min(memStats.chars / Math.max(memStats.trigger_chars, 1), 1);

  return (
    <div className="flex flex-1 min-h-0">
      {/* 侧栏 */}
      <aside className="w-80 shrink-0 border-r bg-white p-4 overflow-y-auto text-sm space-y-4">
        <h2 className="text-base font-semibold">📚 知识库</h2>

        {notesInfo.chunk_count === 0 ? (
          <p className="rounded bg-amber-50 p-2 text-amber-800">
            知识库为空，请上传笔记后重建索引
          </p>
        ) : (
          <p className="rounded bg-emerald-50 p-2 text-emerald-800">
            {notesInfo.notes.length} 篇笔记 · {notesInfo.chunk_count} 个 chunk
          </p>
        )}

        <details className="rounded border p-2" open>
          <summary className="cursor-pointer text-gray-700">
            📄 笔记列表（{notesInfo.notes.length}）
          </summary>
          <ul className="mt-2 space-y-2">
            {notesInfo.notes.length === 0 && <li className="text-gray-400">（还没有笔记）</li>}
            {notesInfo.notes.map((n) => (
              <li key={n.name} className="text-xs">
                <div className="font-medium">{n.name}</div>
                {n.tags.length > 0 && (
                  <div className="mt-1 text-gray-500">
                    🏷️{" "}
                    {n.tags.map((t) => (
                      <code
                        key={t}
                        className="mx-0.5 rounded bg-gray-100 px-1 text-[10px]"
                      >
                        {t}
                      </code>
                    ))}
                  </div>
                )}
                {n.summary && <div className="mt-1 text-gray-500">📝 {n.summary}</div>}
              </li>
            ))}
          </ul>
        </details>

        <div>
          <h3 className="font-medium">📤 上传笔记</h3>
          <input
            type="file"
            accept=".md,.markdown"
            multiple
            disabled={ingesting}
            onChange={(e) => uploadAndIngest(e.target.files)}
            className="mt-2 block w-full text-xs"
          />
          <button
            onClick={rebuildOnly}
            disabled={ingesting}
            className="mt-2 w-full rounded bg-blue-600 py-1.5 text-white text-xs font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            🔄 仅重建索引
          </button>
          {notice && (
            <p className="mt-2 rounded bg-gray-100 p-2 text-xs text-gray-700">{notice}</p>
          )}
        </div>

        <div>
          <h3 className="font-medium">🧠 对话记忆</h3>
          <div className="mt-1 text-xs text-gray-500">
            {memStats.n_messages} 条消息 · {memStats.chars} / {memStats.trigger_chars} 字符
          </div>
          <div className="mt-1 h-1.5 w-full overflow-hidden rounded bg-gray-200">
            <div
              className="h-full bg-blue-500 transition-all"
              style={{ width: `${memRatio * 100}%` }}
            />
          </div>
          <button
            onClick={clearHistory}
            disabled={streaming}
            className="mt-2 w-full rounded border py-1.5 text-xs hover:bg-gray-100 disabled:opacity-50"
          >
            🧹 清空对话历史
          </button>
        </div>

        <div className="pt-3 text-xs text-gray-400 border-t">
          agents-web · <a className="underline" href="https://github.com/Gip886/agents">GitHub</a>
        </div>
      </aside>

      {/* 主聊天区 */}
      <section className="flex flex-1 min-h-0 flex-col">
        <header className="border-b bg-white px-6 py-3">
          <h1 className="text-lg font-bold">🤖 Knowledge Agent</h1>
          <p className="text-xs text-gray-500">
            RAG + Tool Use + 记忆压缩 + ReAct + 联网兜底 · Next.js 版
          </p>
        </header>

        <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto px-6 py-4 space-y-4">
          {history.length === 0 && !active && (
            <div className="mx-auto max-w-md rounded-lg border border-dashed p-6 text-center text-sm text-gray-500">
              问问你的笔记，例如：<br />
              <code className="rounded bg-gray-100 px-1">
                我笔记里 Go 的错误处理怎么讲的？
              </code>
            </div>
          )}
          {history.map((m) => (
            <Message key={m.id} msg={m} />
          ))}
          {active && <ActiveMessage active={active} />}
        </div>

        <footer className="border-t bg-white px-6 py-3">
          <div className="flex gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKey}
              placeholder={streaming ? "生成中…" : "问问你的笔记（Shift+Enter 换行）"}
              disabled={streaming}
              rows={2}
              className="flex-1 resize-none rounded border p-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:bg-gray-50"
            />
            <button
              onClick={submit}
              disabled={streaming || !input.trim()}
              className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {streaming ? "…" : "发送"}
            </button>
          </div>
        </footer>
      </section>
    </div>
  );
}

// ============================================================
// Sub-components
// ============================================================

function Message({ msg }: { msg: ChatMsg }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-lg px-4 py-3 whitespace-pre-wrap text-sm shadow-sm ${
          isUser ? "bg-blue-600 text-white" : "bg-white border"
        }`}
      >
        <div>{msg.content}</div>
        {msg.turn && <TurnTrace turn={msg.turn} />}
      </div>
    </div>
  );
}

function ActiveMessage({ active }: { active: ActiveTurn }) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-lg border bg-white px-4 py-3 whitespace-pre-wrap text-sm shadow-sm">
        {active.activeToolNames.length > 0 && (
          <div className="mb-2 rounded bg-blue-50 px-2 py-1 text-xs text-blue-700">
            🔧 正在调用：{active.activeToolNames.join(", ")}…
          </div>
        )}
        {active.answer ? (
          <div>
            {active.answer}
            <span className="ml-0.5 inline-block w-1.5 h-4 bg-gray-500 animate-pulse align-middle" />
          </div>
        ) : (
          <div className="text-gray-500 text-xs">🤔 思考中…</div>
        )}
        {/* 展示已完成工具轨迹 */}
        <FinishedToolsFromEvents events={active.events} />
      </div>
    </div>
  );
}

function FinishedToolsFromEvents({ events }: { events: TurnEvent[] }) {
  const rounds = new Map<number, { thought: string; calls: { name: string; args: string; result?: string }[] }>();
  for (const e of events) {
    if (e.type === "tool_call_start") {
      const r = rounds.get(e.round) ?? { thought: "", calls: [] };
      r.calls.push({ name: e.name, args: e.arguments });
      rounds.set(e.round, r);
    } else if (e.type === "tool_call_result") {
      const r = rounds.get(e.round);
      if (r) {
        const last = r.calls.reverse().find((c) => c.name === e.name && c.result === undefined);
        r.calls.reverse();
        if (last) last.result = e.result;
      }
    }
  }
  if (rounds.size === 0) return null;
  return (
    <div className="mt-3 space-y-2">
      {[...rounds.entries()].map(([roundNum, r]) => (
        <details key={roundNum} className="rounded border bg-gray-50 text-xs">
          <summary className="cursor-pointer px-2 py-1 text-gray-600">
            第 {roundNum} 轮 · {r.calls.map((c) => c.name).join(", ")}
          </summary>
          <div className="space-y-1 px-2 py-1">
            {r.calls.map((c, i) => (
              <div key={i}>
                <div className="font-mono text-[11px] text-gray-800">
                  🔧 <b>{c.name}</b>
                  <span className="text-gray-500"> {c.args}</span>
                </div>
                {c.result && (
                  <pre className="mt-0.5 max-h-40 overflow-auto rounded bg-white p-1 text-[10px] text-gray-600 whitespace-pre-wrap">
                    {c.result.slice(0, 800)}
                    {c.result.length > 800 && "…"}
                  </pre>
                )}
              </div>
            ))}
          </div>
        </details>
      ))}
    </div>
  );
}

function TurnTrace({ turn }: { turn: TurnResult }) {
  const roundsWithTools = turn.rounds.filter((r) => r.tool_calls.length > 0);
  return (
    <div className="mt-3 space-y-2 text-xs">
      {roundsWithTools.map((r) => (
        <details key={r.round_num} className="rounded border bg-gray-50 open:pb-1">
          <summary className="cursor-pointer px-2 py-1 text-gray-600">
            第 {r.round_num} 轮 · {r.tool_calls.map((tc) => tc.name).join(", ")}
          </summary>
          <div className="px-2 space-y-2">
            {r.thought && (
              <div className="rounded bg-white px-2 py-1 text-gray-700">
                💭 <b>思考</b>：{r.thought}
              </div>
            )}
            {r.tool_calls.map((tc, i) => (
              <div key={i}>
                <div className="font-mono text-[11px] text-gray-800">
                  🔧 <b>{tc.name}</b>
                  <span className="text-gray-500"> {tc.arguments}</span>
                </div>
                <pre className="mt-1 max-h-40 overflow-auto rounded bg-white p-1 text-[10px] text-gray-600 whitespace-pre-wrap">
                  {tc.result.slice(0, 800)}
                  {tc.result.length > 800 && "…"}
                </pre>
              </div>
            ))}
          </div>
        </details>
      ))}
      <div className="text-gray-500">
        📊 {turn.rounds.length} 轮 · {turn.total_tool_calls} 次工具调用 · {turn.total_tokens} tokens
      </div>
      {turn.compression_event && (
        <div className="rounded bg-blue-50 p-2 text-blue-800">
          🧠 <b>记忆压缩</b>：{turn.compression_event.before_msgs} 条 /{" "}
          {turn.compression_event.before_chars} 字符 → {turn.compression_event.after_msgs} 条 /{" "}
          {turn.compression_event.after_chars} 字符
          <div className="mt-1 text-blue-700 text-[11px]">
            摘要：{turn.compression_event.summary_preview}
          </div>
        </div>
      )}
    </div>
  );
}
