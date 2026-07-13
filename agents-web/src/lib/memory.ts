/**
 * 对话记忆管理（对齐 day7/memory.py）
 *
 * 核心思想：
 *   - system prompt 永远保留（messages[0]）
 *   - 最近 KEEP_RECENT_ROUNDS 轮完整对话保留
 *   - 中间旧对话，超过 TRIGGER_CHARS 时交给 LLM 摘要成一条 system 消息
 *
 * 关键坑：压缩必须在轮次边界（user 消息处）切分，不能切在 tool_call 中间，
 *        否则 OpenAI API 会以 "tool_calls must be followed by tool" 报错。
 */
import type OpenAI from "openai";
import type { ChatCompletionMessageParam } from "openai/resources/chat/completions";

import { MEMORY_KEEP_RECENT_ROUNDS, MEMORY_TRIGGER_CHARS } from "./config";

export type ChatMsg = ChatCompletionMessageParam;

export type CompressionEvent = {
  before_chars: number;
  after_chars: number;
  before_msgs: number;
  after_msgs: number;
  summary_preview: string;
};

// —— 粗算一条消息的字符数（够用就行；不做精确 token 化） ——
function msgChars(m: ChatMsg): number {
  let n = 0;
  const content = m.content;
  if (typeof content === "string") n += content.length;
  const tcs = (m as { tool_calls?: { function: { name: string; arguments: string } }[] }).tool_calls;
  if (tcs) {
    for (const tc of tcs) {
      n += (tc.function?.arguments ?? "").length;
      n += (tc.function?.name ?? "").length;
    }
  }
  return n;
}

export type SummarizeFn = (messagesToCompress: ChatMsg[]) => Promise<string>;

export class ConversationMemory {
  readonly systemPrompt: string;
  readonly triggerChars: number;
  readonly keepRecentRounds: number;
  private summarize: SummarizeFn;
  private messages: ChatMsg[];

  constructor(opts: {
    systemPrompt: string;
    summarize: SummarizeFn;
    triggerChars?: number;
    keepRecentRounds?: number;
  }) {
    this.systemPrompt = opts.systemPrompt;
    this.summarize = opts.summarize;
    this.triggerChars = opts.triggerChars ?? MEMORY_TRIGGER_CHARS;
    this.keepRecentRounds = opts.keepRecentRounds ?? MEMORY_KEEP_RECENT_ROUNDS;
    this.messages = [{ role: "system", content: this.systemPrompt }];
  }

  append(msg: ChatMsg) {
    this.messages.push(msg);
  }

  getMessages(): ChatMsg[] {
    return this.messages;
  }

  totalChars(): number {
    return this.messages.reduce((sum, m) => sum + msgChars(m), 0);
  }

  clear() {
    this.messages = [{ role: "system", content: this.systemPrompt }];
  }

  stats(): { n_messages: number; chars: number; trigger_chars: number } {
    return {
      n_messages: this.messages.length,
      chars: this.totalChars(),
      trigger_chars: this.triggerChars,
    };
  }

  /**
   * 若超阈值则压缩。返回压缩事件用于 UI 显示；未压缩返回 null。
   */
  async maybeCompress(): Promise<CompressionEvent | null> {
    if (this.totalChars() < this.triggerChars) return null;

    // 跳过前置 system 消息（原始 prompt + 可能已有的旧摘要）
    let firstScan = 1;
    while (firstScan < this.messages.length && this.messages[firstScan].role === "system") {
      firstScan++;
    }

    // 找所有 user 消息下标（每个 user = 一轮起点，切在这里安全）
    const roundStarts: number[] = [];
    for (let i = firstScan; i < this.messages.length; i++) {
      if (this.messages[i].role === "user") roundStarts.push(i);
    }

    if (roundStarts.length <= this.keepRecentRounds) return null;

    const keepFrom = roundStarts[roundStarts.length - this.keepRecentRounds];

    // 把 system prompt 找出来
    const oldPrefix = this.messages.slice(0, keepFrom).filter((m) => m.role === "system");
    const oldConvo = this.messages.slice(oldPrefix.length, keepFrom);
    const recent = this.messages.slice(keepFrom);

    if (oldConvo.length === 0) return null;

    const beforeChars = this.totalChars();
    const beforeMsgs = this.messages.length;

    const summaryText = await this.summarize(oldConvo);
    const summaryMsg: ChatMsg = {
      role: "system",
      content: `[对话历史摘要 — ${oldConvo.length} 条旧消息已压缩]\n${summaryText}`,
    };

    // 重组：原始 system prompt + 新摘要 + 最近轮次
    this.messages = [this.messages[0], summaryMsg, ...recent];

    const afterChars = this.totalChars();
    const afterMsgs = this.messages.length;

    return {
      before_chars: beforeChars,
      after_chars: afterChars,
      before_msgs: beforeMsgs,
      after_msgs: afterMsgs,
      summary_preview: summaryText.slice(0, 120) + (summaryText.length > 120 ? "..." : ""),
    };
  }
}

/**
 * 返回一个 summarize 函数：用同一套 openai client 生成摘要。
 */
export function makeLlmSummarizer(client: OpenAI, model: string): SummarizeFn {
  return async (msgs: ChatMsg[]) => {
    // 把待压缩消息转成叙述文本
    const lines: string[] = [];
    for (const m of msgs) {
      const content = typeof m.content === "string" ? m.content : "";
      if (m.role === "user") {
        lines.push(`用户: ${content}`);
      } else if (m.role === "assistant") {
        const tcs = (m as { tool_calls?: { function: { name: string; arguments: string } }[] }).tool_calls;
        if (tcs) {
          const calls = tcs.map((tc) => `${tc.function.name}(${tc.function.arguments})`);
          lines.push(`助手[调用工具]: ${calls.join("; ")}`);
        }
        if (content) lines.push(`助手: ${content}`);
      } else if (m.role === "tool") {
        const trimmed = content.slice(0, 200) + (content.length > 200 ? "..." : "");
        lines.push(`工具返回: ${trimmed}`);
      } else if (m.role === "system") {
        lines.push(`[之前摘要] ${content}`);
      }
    }
    const conversationText = lines.join("\n");

    const prompt =
      "下面是一段人机对话的历史片段。请用简洁的中文（不超过 200 字）总结：\n" +
      "1) 用户问过哪些问题\n" +
      "2) 助手做过哪些关键操作、给出了什么核心结论\n" +
      "3) 涉及到了哪些笔记文件（如果有）\n" +
      "只输出摘要正文，不要客套。\n\n" +
      "----对话----\n" +
      conversationText;

    const resp = await client.chat.completions.create({
      model,
      messages: [
        { role: "system", content: "你是一个对话摘要助手，输出精炼、无冗余。" },
        { role: "user", content: prompt },
      ],
      temperature: 0.3,
    });
    return resp.choices[0].message.content ?? "(摘要生成失败)";
  };
}
