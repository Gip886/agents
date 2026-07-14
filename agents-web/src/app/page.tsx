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
  // AbortController：streaming 期间用户点"停止"时 abort() 掉 fetch。
  // 用 ref 不用 state：不参与渲染循环，可避免 StrictMode 重复创建。
  const abortRef = useRef<AbortController | null>(null);

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

    // AbortController：给 fetch 传 signal；用户点"停止"时 abort()
    const controller = new AbortController();
    abortRef.current = controller;

    // 闭包变量：唯一权威真相源。setState updater 只做渲染同步，不做赋值。
    let accumulatedAnswer = "";
    // 显式标注类型 —— 否则 TS 会做 CFA 收窄成 null / ""，认为 callback 里的赋值"不可能发生"
    let finalTurn: TurnResult | null = null as TurnResult | null;
    let streamError: string | null = null as string | null;
    let userAborted = false;

    try {
      await consumeSSE<
        | TurnEvent
        | { type: "error"; message: string }
        | { type: "aborted" }
      >(
        "/api/chat",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text }),
          signal: controller.signal,   // fetch 收到 abort 会 reject
        },
        (evt) => {
          // 先在闭包里维护"真相"，再触发 React 状态更新
          if (evt.type === "answer_delta") {
            accumulatedAnswer += evt.text;
          } else if (evt.type === "turn_done") {
            finalTurn = evt.result;
          } else if (evt.type === "error") {
            streamError = evt.message;
          } else if (evt.type === "aborted") {
            // 后端确认已 abort；前端会显示"(已停止)"
            userAborted = true;
          }

          setActive((prev) => {
            if (!prev) return prev;
            const next: ActiveTurn = { ...prev, events: [...prev.events, evt as TurnEvent] };
            if (evt.type === "answer_delta") {
              next.answer = prev.answer + evt.text;
            } else if (evt.type === "tool_call_start") {
              next.activeToolNames = [...prev.activeToolNames, evt.name];
            } else if (evt.type === "tool_call_result") {
              next.activeToolNames = prev.activeToolNames.filter((n) => n !== evt.name);
            }
            return next;
          });
        },
      );
    } catch (e) {
      // AbortError = 用户主动停止；不当错误显示
      if ((e as Error).name === "AbortError") {
        userAborted = true;
      } else {
        streamError = e instanceof Error ? e.message : String(e);
      }
    } finally {
      abortRef.current = null;
    }

    // 组装最终 history 条目：
    // - 优先用后端 turn_done 里的 answer（可能已 markdown 格式化）
    // - 如果 turn_done 缺失或答案空，退回到"流式累加的字符"
    // - 用户停止时给已流出的字符加个"(已停止)"标签
    // - 都没有再显示错误
    let finalContent: string;
    if (finalTurn?.answer && finalTurn.answer !== "(无回复)") {
      finalContent = finalTurn.answer;
    } else if (accumulatedAnswer) {
      finalContent = userAborted
        ? accumulatedAnswer + "\n\n_(已停止)_"
        : accumulatedAnswer;
    } else if (userAborted) {
      finalContent = "_(已停止，未生成内容)_";
    } else if (streamError) {
      finalContent = `❌ 出错：${streamError}`;
    } else {
      finalContent = "(无回复)";
    }

    setHistory((h) => [
      ...h,
      {
        id: userMsgId + 1,
        role: "assistant",
        content: finalContent,
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

  // —— 用户点"停止"：abort 当前 fetch。fetch reject → submit 走 finally →
  // finalContent 用累加的字符（不覆盖为"(无回复)"）→ streaming 归位
  const stopGeneration = () => {
    abortRef.current?.abort();
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
    <div className="flex flex-1 min-h-0 bg-gray-50">
      {/* 侧栏 */}
      <aside className="w-80 shrink-0 border-r border-gray-200 bg-white p-5 overflow-y-auto text-sm space-y-5">
        <div>
          <h2 className="text-base font-semibold text-gray-900">📚 知识库</h2>

          {notesInfo.chunk_count === 0 ? (
            <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-amber-800 border border-amber-200">
              知识库为空，请上传笔记后重建索引
            </p>
          ) : (
            <p className="mt-3 rounded-md bg-emerald-50 px-3 py-2 text-emerald-800 border border-emerald-200">
              <span className="font-medium">{notesInfo.notes.length}</span> 篇笔记 ·{" "}
              <span className="font-medium">{notesInfo.chunk_count}</span> chunk
            </p>
          )}
        </div>

        <details className="rounded-md border border-gray-200 bg-gray-50/50 p-3" open>
          <summary className="cursor-pointer font-medium text-gray-700">
            笔记列表（{notesInfo.notes.length}）
          </summary>
          <ul className="mt-3 space-y-3">
            {notesInfo.notes.length === 0 && (
              <li className="text-gray-400 text-xs">（还没有笔记）</li>
            )}
            {notesInfo.notes.map((n) => (
              <li key={n.name} className="text-xs">
                <div className="font-medium text-gray-900">{n.name}</div>
                {n.tags.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1 text-gray-500">
                    {n.tags.map((t) => (
                      <code
                        key={t}
                        className="rounded bg-blue-50 px-1.5 py-0.5 text-[10px] text-blue-700 border border-blue-100"
                      >
                        {t}
                      </code>
                    ))}
                  </div>
                )}
                {n.summary && (
                  <div className="mt-1 text-gray-500 line-clamp-3">📝 {n.summary}</div>
                )}
              </li>
            ))}
          </ul>
        </details>

        <div>
          <h3 className="font-medium text-gray-700 mb-2">📤 上传笔记</h3>
          <label className="block rounded-md border-2 border-dashed border-gray-300 bg-gray-50 hover:bg-gray-100 hover:border-gray-400 transition cursor-pointer p-3 text-center text-xs text-gray-500">
            <input
              type="file"
              accept=".md,.markdown"
              multiple
              disabled={ingesting}
              onChange={(e) => uploadAndIngest(e.target.files)}
              className="hidden"
            />
            拖入 / 点击选择 .md 文件
          </label>
          <button
            onClick={rebuildOnly}
            disabled={ingesting}
            className="mt-2 w-full rounded-md bg-blue-600 py-2 text-white text-xs font-medium shadow-sm hover:bg-blue-700 disabled:opacity-50 transition"
          >
            🔄 仅重建索引
          </button>
          {notice && (
            <p className="mt-2 rounded-md bg-gray-100 px-3 py-2 text-xs text-gray-700 border border-gray-200">
              {notice}
            </p>
          )}
        </div>

        <div>
          <h3 className="font-medium text-gray-700 mb-2">🧠 对话记忆</h3>
          <div className="text-xs text-gray-500">
            <span className="font-medium text-gray-700">{memStats.n_messages}</span> 条消息 ·{" "}
            <span className="font-medium text-gray-700">{memStats.chars}</span>
            <span className="text-gray-400"> / {memStats.trigger_chars} 字符</span>
          </div>
          <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-gray-200">
            <div
              className={`h-full transition-all ${memRatio > 0.8 ? "bg-orange-500" : "bg-blue-500"}`}
              style={{ width: `${memRatio * 100}%` }}
            />
          </div>
          <button
            onClick={clearHistory}
            disabled={streaming}
            className="mt-3 w-full rounded-md border border-gray-300 bg-white py-2 text-xs text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition"
          >
            🧹 清空对话历史
          </button>
        </div>

        <div className="pt-4 text-xs text-gray-400 border-t border-gray-200">
          agents-web ·{" "}
          <a className="underline hover:text-gray-600" href="https://github.com/Gip886/agents">
            GitHub
          </a>
        </div>
      </aside>

      {/* 主聊天区 */}
      <section className="flex flex-1 min-h-0 flex-col bg-gray-50">
        <header className="border-b border-gray-200 bg-white px-8 py-4 shadow-sm">
          <h1 className="text-lg font-semibold text-gray-900">🤖 Knowledge Agent</h1>
          <p className="text-xs text-gray-500 mt-0.5">
            RAG + Tool Use + 记忆压缩 + ReAct + 联网兜底 · Next.js 版
          </p>
        </header>

        <div
          ref={scrollRef}
          className="flex-1 min-h-0 overflow-y-auto px-8 py-6 space-y-4"
        >
          {history.length === 0 && !active && (
            <div className="mx-auto max-w-lg mt-12 rounded-xl border border-dashed border-gray-300 bg-white p-8 text-center text-sm text-gray-500 shadow-sm">
              <div className="text-2xl mb-3">👋</div>
              <div className="mb-3">问问你的笔记，例如：</div>
              <code className="inline-block rounded-md bg-gray-100 px-3 py-1.5 text-gray-700 text-xs">
                我笔记里 Go 的错误处理怎么讲的？
              </code>
            </div>
          )}
          {history.map((m) => (
            <Message key={m.id} msg={m} />
          ))}
          {active && <ActiveMessage active={active} />}
        </div>

        <footer className="border-t border-gray-200 bg-white px-8 py-4">
          <div className="flex gap-3 items-end">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKey}
              placeholder={streaming ? "生成中…" : "问问你的笔记（Shift+Enter 换行）"}
              disabled={streaming}
              rows={2}
              className="flex-1 resize-none rounded-xl border border-gray-300 bg-white px-4 py-3 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-blue-400 disabled:bg-gray-50 placeholder:text-gray-400"
            />
            {streaming ? (
              <button
                onClick={stopGeneration}
                className="rounded-xl bg-red-600 px-6 py-3 text-sm font-medium text-white shadow-sm hover:bg-red-700 transition"
              >
                ⏹ 停止
              </button>
            ) : (
              <button
                onClick={submit}
                disabled={!input.trim()}
                className="rounded-xl bg-blue-600 px-6 py-3 text-sm font-medium text-white shadow-sm hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition"
              >
                发送
              </button>
            )}
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
        className={`max-w-[85%] rounded-2xl px-4 py-3 whitespace-pre-wrap text-sm shadow-sm ${
          isUser
            ? "bg-blue-600 text-white"
            : "bg-white border border-gray-200 text-gray-800"
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
      <div className="max-w-[85%] rounded-2xl border border-gray-200 bg-white px-4 py-3 whitespace-pre-wrap text-sm shadow-sm text-gray-800">
        {active.activeToolNames.length > 0 && (
          <div className="mb-2 rounded-md bg-blue-50 border border-blue-100 px-3 py-1.5 text-xs text-blue-700 inline-block">
            🔧 正在调用：
            <span className="font-medium">{active.activeToolNames.join(", ")}</span>…
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
        <details key={roundNum} className="rounded-md border border-gray-200 bg-gray-50 text-xs">
          <summary className="cursor-pointer px-3 py-2 text-gray-700 font-medium">
            第 {roundNum} 轮 · {r.calls.map((c) => c.name).join(", ")}
          </summary>
          <div className="space-y-2 px-3 pb-3">
            {r.calls.map((c, i) => (
              <div key={i}>
                <div className="font-mono text-[11px] text-gray-800">
                  🔧 <b>{c.name}</b>
                  <span className="text-gray-500"> {c.args}</span>
                </div>
                {c.result && (
                  <pre className="mt-1 max-h-40 overflow-auto rounded-md bg-white p-2 text-[10px] text-gray-600 whitespace-pre-wrap border border-gray-200">
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
        <details key={r.round_num} className="rounded-md border border-gray-200 bg-gray-50">
          <summary className="cursor-pointer px-3 py-2 text-gray-700 font-medium">
            第 {r.round_num} 轮 · {r.tool_calls.map((tc) => tc.name).join(", ")}
          </summary>
          <div className="px-3 pb-3 space-y-2">
            {r.thought && (
              <div className="rounded-md bg-blue-50 border border-blue-100 px-3 py-2 text-blue-900">
                💭 <b>思考</b>：{r.thought}
              </div>
            )}
            {r.tool_calls.map((tc, i) => (
              <div key={i}>
                <div className="font-mono text-[11px] text-gray-800">
                  🔧 <b>{tc.name}</b>
                  <span className="text-gray-500"> {tc.arguments}</span>
                </div>
                <pre className="mt-1 max-h-40 overflow-auto rounded-md bg-white p-2 text-[10px] text-gray-600 whitespace-pre-wrap border border-gray-200">
                  {tc.result.slice(0, 800)}
                  {tc.result.length > 800 && "…"}
                </pre>
              </div>
            ))}
          </div>
        </details>
      ))}
      <div className="text-gray-500 pl-1">
        📊 <b>{turn.rounds.length}</b> 轮 · <b>{turn.total_tool_calls}</b> 次工具调用 ·{" "}
        <b>{turn.total_tokens}</b> tokens
      </div>
      {turn.compression_event && (
        <div className="rounded-md bg-purple-50 border border-purple-200 p-3 text-purple-900">
          🧠 <b>记忆压缩</b>：{turn.compression_event.before_msgs} 条 /{" "}
          {turn.compression_event.before_chars} 字符 → {turn.compression_event.after_msgs} 条 /{" "}
          {turn.compression_event.after_chars} 字符
          <div className="mt-1 text-purple-700 text-[11px]">
            摘要：{turn.compression_event.summary_preview}
          </div>
        </div>
      )}
    </div>
  );
}
