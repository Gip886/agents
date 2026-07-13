/**
 * KnowledgeAgent —— 引擎层（对齐 day7/agent.py）。
 *
 * Web 版直接实现流式版本 `runTurnStream()`（async generator），yield 一系列事件；
 * 前端消费 SSE，UI 逐字显示。参见 docs/streaming-notes.md 里的设计。
 */
import OpenAI from "openai";
import type { ChatCompletionMessageParam } from "openai/resources/chat/completions";

import {
  ARK_API_KEY,
  ARK_BASE_URL,
  ARK_ENDPOINT_ID,
  MAX_ROUNDS,
} from "./config";
import { ConversationMemory, makeLlmSummarizer } from "./memory";
import type { CompressionEvent } from "./memory";
import { executeTool, TOOLS_SCHEMA, type ToolContext } from "./tools";

// ============================================================
// System prompt（和 day7 一致，中文回答）
// ============================================================

export const SYSTEM_PROMPT = `你是一个基于用户私人笔记的知识助手。用户会问你问题，你有以下工具：

【本地笔记只读工具】
- search_notes(query, top_k)：语义检索笔记，返回相关片段
- read_full_note(filename)：读一篇笔记的完整原文
- list_notes()：列出所有笔记文件名
- list_tags()：列出所有笔记的标签和已保存的摘要（概览用）

【本地笔记写入工具】—— 会修改笔记文件
- add_tag(filename, tags)：给笔记加标签（写回 frontmatter）
- summarize_note(filename)：让 LLM 生成摘要并保存到笔记 frontmatter

【联网工具】
- web_search(query, max_results)：Tavily 联网搜索。**兜底用**：本地笔记里找不到、
  或用户问的是笔记里不可能有的事（今天的新闻、某个库的最新版本等）时才用。

工作原则：

1. **优先查本地笔记**。用户问的每个具体问题，先 search_notes；只有搜不到（相似度 < 0.4）
   或问题明显和笔记无关时，才考虑 web_search。**不要跳过本地直接联网**。
2. **⚠️ 关键：每次调用工具时，assistant 消息的 content 字段必须非空**。用一句中文写清楚
   "我打算做什么、为什么"（这就是 Thought / ReAct 的 Reasoning 部分）。这条要严格遵守，
   便于用户看到你的推理。示例：
     content = "先在笔记里搜 Go 错误处理，看看 go-tips.md 里怎么讲。"
     tool_calls = [{name: "search_notes", ...}]
   **不要输出空 content 就调工具**，即使你觉得下一步很显然。
3. **回答时要引用来源**：本地用 \`[来源: xxx.md]\` / \`[来源: xxx.md#N]\`；
   联网用 \`[来源: <URL>]\`。混合来源都要标。
4. **如果本地和联网都找不到，明确告诉用户**"没找到相关内容"，不要瞎编。
5. **一次可以并行调用多个工具**以提高效率。
6. **写入工具要谨慎**：只有用户明确说"加标签"、"保存摘要"时才调用 add_tag / summarize_note。
   仅仅想看总结时用 read_full_note 自己总结即可。
7. 简单闲聊、通用问题不需要用工具。

回答风格：简洁、准确、有引用。中文回答。`;

// ============================================================
// 结构化 Trace（UI 消费）
// ============================================================

export type ToolCallTrace = {
  name: string;
  arguments: string;
  result: string;
};

export type RoundTrace = {
  round_num: number;
  thought: string;
  tool_calls: ToolCallTrace[];
  assistant_text: string;
  prompt_tokens: number;
  completion_tokens: number;
};

export type TurnResult = {
  answer: string;
  rounds: RoundTrace[];
  compression_event: CompressionEvent | null;
  total_tool_calls: number;
  total_tokens: number;
};

// ============================================================
// 流式事件
// ============================================================

export type TurnEvent =
  | { type: "thought_delta"; text: string }
  | { type: "answer_delta"; text: string }
  | { type: "tool_call_start"; name: string; arguments: string; round: number }
  | { type: "tool_call_result"; name: string; result: string; round: number }
  | { type: "round_done"; round_num: number }
  | { type: "turn_done"; result: TurnResult };

// ============================================================
// KnowledgeAgent
// ============================================================

export class KnowledgeAgent {
  readonly client: OpenAI;
  readonly model: string;
  readonly maxRounds: number;
  readonly memory: ConversationMemory;
  private toolCtx: ToolContext;

  constructor(opts?: { systemPrompt?: string; maxRounds?: number }) {
    if (!ARK_API_KEY) throw new Error("ARK_API_KEY 未设置");
    if (!ARK_ENDPOINT_ID) throw new Error("ARK_ENDPOINT_ID 未设置");

    this.client = new OpenAI({ apiKey: ARK_API_KEY, baseURL: ARK_BASE_URL });
    this.model = ARK_ENDPOINT_ID;
    this.maxRounds = opts?.maxRounds ?? MAX_ROUNDS;

    this.memory = new ConversationMemory({
      systemPrompt: opts?.systemPrompt ?? SYSTEM_PROMPT,
      summarize: makeLlmSummarizer(this.client, this.model),
    });
    this.toolCtx = { client: this.client, chatModel: this.model };
  }

  clearMemory() {
    this.memory.clear();
  }

  memoryStats() {
    return this.memory.stats();
  }

  // ---------- 核心：流式跑一轮对话 ----------

  async *runTurnStream(userInput: string): AsyncGenerator<TurnEvent> {
    this.memory.append({ role: "user", content: userInput });
    const rounds: RoundTrace[] = [];

    for (let roundNum = 1; roundNum <= this.maxRounds; roundNum++) {
      const roundTrace: RoundTrace = {
        round_num: roundNum,
        thought: "",
        tool_calls: [],
        assistant_text: "",
        prompt_tokens: 0,
        completion_tokens: 0,
      };

      const stream = await this.client.chat.completions.create({
        model: this.model,
        messages: this.memory.getMessages(),
        tools: TOOLS_SCHEMA,
        stream: true,
        stream_options: { include_usage: true },
      });

      // —— 累加器：拼出完整 assistant 消息 ——
      let contentBuf = "";
      let reasoningBuf = "";
      const toolCallsBuf: Record<
        number,
        { id: string | null; name: string; arguments: string }
      > = {};
      let usage: { prompt_tokens: number; completion_tokens: number } | null = null;

      for await (const chunk of stream) {
        if (chunk.usage) {
          usage = {
            prompt_tokens: chunk.usage.prompt_tokens,
            completion_tokens: chunk.usage.completion_tokens,
          };
        }
        if (!chunk.choices || chunk.choices.length === 0) continue;
        const delta = chunk.choices[0].delta;

        // (1) content 分片 —— 最终答案在这里
        if (typeof delta.content === "string" && delta.content) {
          contentBuf += delta.content;
          yield { type: "answer_delta", text: delta.content };
        }

        // (2) Doubao 的 reasoning_content 分片（内部推理链）
        const rc = (delta as { reasoning_content?: string | null }).reasoning_content;
        if (typeof rc === "string" && rc) {
          reasoningBuf += rc;
          yield { type: "thought_delta", text: rc };
        }

        // (3) tool_calls 分片 —— 必须按 index 归类
        if (delta.tool_calls) {
          for (const tc of delta.tool_calls) {
            const idx = tc.index;
            if (!toolCallsBuf[idx]) {
              toolCallsBuf[idx] = { id: null, name: "", arguments: "" };
            }
            const slot = toolCallsBuf[idx];
            if (tc.id) slot.id = tc.id;
            if (tc.function?.name) slot.name += tc.function.name;
            if (tc.function?.arguments) slot.arguments += tc.function.arguments;
          }
        }
      }

      // —— 流结束，把 assistant 消息 append 到 memory ——
      const toolCallList = Object.values(toolCallsBuf);
      const assistantMsg: ChatCompletionMessageParam & {
        tool_calls?: {
          id: string;
          type: "function";
          function: { name: string; arguments: string };
        }[];
      } = {
        role: "assistant",
        content: contentBuf || null,
      };
      if (toolCallList.length > 0) {
        assistantMsg.tool_calls = toolCallList.map((s) => ({
          id: s.id ?? "",
          type: "function" as const,
          function: { name: s.name, arguments: s.arguments },
        }));
      }
      this.memory.append(assistantMsg);

      if (usage) {
        roundTrace.prompt_tokens = usage.prompt_tokens;
        roundTrace.completion_tokens = usage.completion_tokens;
      }

      // —— 没有 tool_calls：这就是最终答案，收工 ——
      if (toolCallList.length === 0) {
        roundTrace.assistant_text = contentBuf || "(无回复)";
        rounds.push(roundTrace);
        // 压缩独立 try/catch：压缩失败不能杀掉 turn（答案已经流出去了）
        let compression: CompressionEvent | null = null;
        try {
          compression = await this.memory.maybeCompress();
        } catch (e) {
          console.error("[maybeCompress] failed:", e);
        }
        const result = this.buildResult(contentBuf || "(无回复)", rounds, compression);
        yield { type: "turn_done", result };
        return;
      }

      // —— 有 tool_calls：先固化 Thought ——
      let thought = contentBuf.trim();
      if (!thought && reasoningBuf) {
        // reasoning_content 通常很长；取首段并截 240 字
        const firstPara = reasoningBuf.split("\n", 1)[0].trim();
        thought = firstPara.length > 240 ? firstPara.slice(0, 240) + "…" : firstPara;
      }
      roundTrace.thought = thought;

      // —— 执行工具（并发跑，与 Python 版顺序一致：yield start → 执行 → yield result） ——
      for (const slot of toolCallList) {
        yield {
          type: "tool_call_start",
          name: slot.name,
          arguments: slot.arguments,
          round: roundNum,
        };
        const result = await executeTool(slot.name, slot.arguments, this.toolCtx);
        roundTrace.tool_calls.push({
          name: slot.name,
          arguments: slot.arguments,
          result,
        });
        this.memory.append({
          role: "tool",
          tool_call_id: slot.id ?? "",
          content: result,
        });
        yield {
          type: "tool_call_result",
          name: slot.name,
          result,
          round: roundNum,
        };
      }
      rounds.push(roundTrace);
      yield { type: "round_done", round_num: roundNum };
    }

    // —— 走完 maxRounds 还没结束 ——
    let compression: CompressionEvent | null = null;
    try {
      compression = await this.memory.maybeCompress();
    } catch (e) {
      console.error("[maybeCompress] failed:", e);
    }
    const result = this.buildResult(
      `⚠️ 超过最大轮次 ${this.maxRounds}，可能陷入循环`,
      rounds,
      compression,
    );
    yield { type: "turn_done", result };
  }

  private buildResult(
    answer: string,
    rounds: RoundTrace[],
    compression: CompressionEvent | null,
  ): TurnResult {
    const totalToolCalls = rounds.reduce((s, r) => s + r.tool_calls.length, 0);
    const totalTokens = rounds.reduce(
      (s, r) => s + r.prompt_tokens + r.completion_tokens,
      0,
    );
    return {
      answer,
      rounds,
      compression_event: compression,
      total_tool_calls: totalToolCalls,
      total_tokens: totalTokens,
    };
  }
}

// ============================================================
// 单例 —— 保证同一进程内 memory 不丢
// dev 模式 Next.js 会热重载，所以挂到 globalThis 上防重建
// ============================================================

const g = globalThis as unknown as { _knowledgeAgent?: KnowledgeAgent };

export function getAgent(): KnowledgeAgent {
  if (!g._knowledgeAgent) {
    g._knowledgeAgent = new KnowledgeAgent();
  }
  return g._knowledgeAgent;
}
