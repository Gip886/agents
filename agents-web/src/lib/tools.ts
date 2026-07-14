/**
 * 工具集（对齐 day7/tools.py 的 7 个工具）
 *
 * 每个工具都是 async 函数，签名统一：(ctx, args) -> string 结果。
 * ctx 提供 OpenAI client + chat model —— 因为 summarize_note 要调 LLM。
 *
 * 所有异常都被 execute_tool 转成字符串返回给 LLM，让 Agent 自行决策而不是崩溃。
 */
import type OpenAI from "openai";
import type { ChatCompletionTool } from "openai/resources/chat/completions";

import { TAVILY_API_KEY } from "./config";
import * as kb from "./kb";

export type ToolContext = {
  client: OpenAI;
  chatModel: string;
  /** 用于中断长跑工具（比如 web_search）。可选 —— agent 每轮传下来 */
  signal?: AbortSignal;
};

// ============================================================
// 工具实现
// ============================================================

async function toolSearchNotes(
  _ctx: ToolContext,
  args: { query: string; top_k?: number },
): Promise<string> {
  const results = await kb.search(args.query, args.top_k ?? 3);
  if (results.length === 0) return "未找到相关笔记内容。";

  const lines = [`检索关键词: '${args.query}'，找到 ${results.length} 个片段：\n`];
  results.forEach((r, i) => {
    lines.push(
      `[${i + 1}] 来源: ${r.file}#${r.chunk_idx}  相似度: ${r.similarity}\n内容:\n${r.text}\n`,
    );
  });
  return lines.join("\n");
}

async function toolReadFullNote(_ctx: ToolContext, args: { filename: string }): Promise<string> {
  try {
    return kb.readFullNote(args.filename);
  } catch (e) {
    return `ERROR: ${(e as Error).message}\n可用笔记：${kb.listNotes().join(", ")}`;
  }
}

async function toolListNotes(): Promise<string> {
  const notes = kb.listNotes();
  if (notes.length === 0) return "notes/ 目录下没有笔记文件。";
  return "所有笔记文件：\n" + notes.map((n) => `  - ${n}`).join("\n");
}

async function toolListTags(): Promise<string> {
  const notes = kb.listNotes();
  if (notes.length === 0) return "notes/ 目录下没有笔记文件。";

  const lines = [`共 ${notes.length} 篇笔记：`];
  for (const name of notes) {
    let meta: Record<string, string | string[]> = {};
    try {
      meta = kb.readMeta(name);
    } catch {
      // 忽略单个失败
    }
    const tags = Array.isArray(meta.tags) ? meta.tags : [];
    const summary = typeof meta.summary === "string" ? meta.summary : "(无摘要)";
    const tagStr = tags.length > 0 ? tags.join(", ") : "(无标签)";
    lines.push(`  - ${name}`);
    lines.push(`      tags: ${tagStr}`);
    lines.push(`      summary: ${summary}`);
  }
  return lines.join("\n");
}

async function toolAddTag(
  _ctx: ToolContext,
  args: { filename: string; tags: string[] },
): Promise<string> {
  if (!Array.isArray(args.tags) || !args.tags.every((t) => typeof t === "string")) {
    return 'ERROR: tags 必须是字符串列表，例如 ["go", "error-handling"]';
  }
  const cleaned = args.tags.map((t) => t.trim().toLowerCase()).filter(Boolean);
  if (cleaned.length === 0) return "ERROR: 没有有效标签";

  try {
    const meta = kb.updateMeta(args.filename, { tags: cleaned });
    return `已给 ${args.filename} 添加标签。当前所有标签: ${JSON.stringify(meta.tags ?? [])}`;
  } catch (e) {
    return `ERROR: ${(e as Error).message}\n可用笔记：${kb.listNotes().join(", ")}`;
  }
}

async function toolSummarizeNote(
  ctx: ToolContext,
  args: { filename: string },
): Promise<string> {
  let text: string;
  try {
    text = kb.readFullNote(args.filename);
  } catch (e) {
    return `ERROR: ${(e as Error).message}\n可用笔记：${kb.listNotes().join(", ")}`;
  }

  const prompt =
    "下面是一篇笔记的原文。请用不超过 100 字的中文写一句话摘要，" +
    "只写摘要正文，不要客套：\n\n" +
    `----原文----\n${text}`;

  let summary: string;
  try {
    const resp = await ctx.client.chat.completions.create({
      model: ctx.chatModel,
      messages: [
        { role: "system", content: "你是一个精准的摘要生成器。" },
        { role: "user", content: prompt },
      ],
      temperature: 0.3,
    });
    summary = (resp.choices[0].message.content ?? "").trim();
  } catch (e) {
    return `ERROR: LLM 调用失败：${(e as Error).message}`;
  }
  if (!summary) return "ERROR: 生成的摘要为空";

  try {
    kb.updateMeta(args.filename, { summary });
  } catch (e) {
    return `ERROR: 摘要生成成功但写回失败：${(e as Error).message}\n摘要内容: ${summary}`;
  }
  return `已为 ${args.filename} 生成并保存摘要：\n${summary}`;
}

async function toolWebSearch(
  ctx: ToolContext,
  args: { query: string; max_results?: number },
): Promise<string> {
  if (!TAVILY_API_KEY) {
    return (
      "ERROR: 未配置 TAVILY_API_KEY。请在 .env.local 里加一行 " +
      "`TAVILY_API_KEY=tvly-xxx`（去 tavily.com 免费申请，1000 次/月）。"
    );
  }
  if (typeof args.query !== "string" || !args.query.trim()) {
    return "ERROR: query 不能为空";
  }
  const maxResults = Math.max(1, Math.min(args.max_results ?? 3, 10));

  // 组合中断信号：用户 abort OR 15s 超时。AbortSignal.any 需 Node 20+
  const timeoutSignal = AbortSignal.timeout(15000);
  const signal = ctx.signal
    ? AbortSignal.any([ctx.signal, timeoutSignal])
    : timeoutSignal;

  let data: {
    results?: { title?: string; url?: string; content?: string }[];
    answer?: string;
  };
  try {
    const resp = await fetch("https://api.tavily.com/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        api_key: TAVILY_API_KEY,
        query: args.query,
        max_results: maxResults,
        search_depth: "basic",
        include_answer: true,
      }),
      signal,
    });
    if (!resp.ok) {
      const text = await resp.text();
      return `ERROR: Tavily HTTP ${resp.status}: ${text.slice(0, 200)}`;
    }
    data = await resp.json();
  } catch (e) {
    return `ERROR: Tavily 请求失败：${(e as Error).message}`;
  }

  const results = data.results ?? [];
  if (results.length === 0) return `联网搜索 '${args.query}' 没有结果。`;

  const lines = [`🌐 联网搜索: '${args.query}'，返回 ${results.length} 条结果：`];
  const answer = (data.answer ?? "").trim();
  if (answer) lines.push(`\n📌 Tavily 一句话答案: ${answer}\n`);

  results.forEach((r, i) => {
    let content = (r.content ?? "").trim();
    if (content.length > 500) content = content.slice(0, 500) + "…";
    lines.push(`\n[${i + 1}] ${r.title ?? ""}\n  URL: ${r.url ?? ""}\n  摘要: ${content}`);
  });
  return lines.join("\n");
}

// ============================================================
// 工具注册表
// ============================================================

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type ToolImpl = (ctx: ToolContext, args: any) => Promise<string>;

const TOOL_IMPLEMENTATIONS: Record<string, ToolImpl> = {
  search_notes: toolSearchNotes,
  read_full_note: toolReadFullNote,
  list_notes: toolListNotes,
  list_tags: toolListTags,
  add_tag: toolAddTag,
  summarize_note: toolSummarizeNote,
  web_search: toolWebSearch,
};

// ============================================================
// 工具 Schema
// ============================================================

export const TOOLS_SCHEMA: ChatCompletionTool[] = [
  {
    type: "function",
    function: {
      name: "search_notes",
      description:
        "语义检索用户的私人笔记，返回与查询最相关的几个片段。" +
        "**每当用户问的问题涉及'我的笔记里写了什么'、需要引用笔记内容时，优先使用此工具**。" +
        "支持自然语言查询，不需要关键词精确匹配。" +
        "返回的每个片段包含：来源文件、chunk 位置、相似度分数、内容。" +
        "如果相似度都低于 0.4，说明可能笔记里没写相关内容。",
      parameters: {
        type: "object",
        properties: {
          query: { type: "string", description: "查询问题或关键词，用自然语言即可。" },
          top_k: { type: "integer", description: "返回几个最相关的片段。默认 3。范围 1-10。" },
        },
        required: ["query"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "read_full_note",
      description:
        "读取一篇笔记的完整原文。" +
        "**当 search_notes 返回的片段不够完整、或用户想要看某篇笔记全貌时使用**。" +
        "输入的是文件名（不带路径），例如 'go-tips.md'。",
      parameters: {
        type: "object",
        properties: {
          filename: { type: "string", description: "笔记文件名，例如 'go-tips.md'（不要带 notes/ 前缀）" },
        },
        required: ["filename"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "list_notes",
      description:
        "列出所有笔记文件的名字。" +
        "**当用户问'我笔记里都有哪些内容'、或者你需要知道有哪些文件可用时使用**。",
      parameters: { type: "object", properties: {}, required: [] },
    },
  },
  {
    type: "function",
    function: {
      name: "add_tag",
      description:
        "给一篇笔记添加一个或多个标签。标签会写入笔记文件头部的 frontmatter，永久保存。" +
        "**当用户说'给这篇笔记加个标签 xxx'时使用**。" +
        "已存在的标签不会重复添加。标签会被规范化为小写。",
      parameters: {
        type: "object",
        properties: {
          filename: { type: "string", description: "笔记文件名" },
          tags: {
            type: "array",
            items: { type: "string" },
            description: "要添加的标签列表，例如 ['go', 'backend']",
          },
        },
        required: ["filename", "tags"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "summarize_note",
      description:
        "生成一篇笔记的一句话摘要（不超过 100 字），并保存到笔记的 frontmatter。" +
        "**当用户明确要求'给 xxx 生成摘要'、'总结一下 xxx'并希望摘要被保存下来时使用**。" +
        "如果用户只是要看总结、不需要保存，你可以直接用 read_full_note 读全文后自己总结，不要用这个工具。",
      parameters: {
        type: "object",
        properties: { filename: { type: "string", description: "笔记文件名" } },
        required: ["filename"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "list_tags",
      description:
        "列出所有笔记的标签和已保存的摘要。" +
        "**当用户问'我笔记有哪些主题/分类'、或想了解笔记全景时使用**。",
      parameters: { type: "object", properties: {}, required: [] },
    },
  },
  {
    type: "function",
    function: {
      name: "web_search",
      description:
        "联网搜索（Tavily）。**兜底工具**：只在本地笔记里明确没有相关内容" +
        "（比如你先用 search_notes 搜过、相似度都 < 0.4，或用户问的是笔记里不可能有的事" +
        "，如今天的新闻、某个库的最新版本）时才使用。" +
        "不要一上来就 web_search —— 用户笔记里可能有更贴合他自己上下文的答案。",
      parameters: {
        type: "object",
        properties: {
          query: { type: "string", description: "搜索查询，用自然语言" },
          max_results: { type: "integer", description: "返回结果数，默认 3，范围 1-10" },
        },
        required: ["query"],
      },
    },
  },
];

// ============================================================
// 统一执行入口
// ============================================================

export async function executeTool(
  name: string,
  argumentsJson: string,
  ctx: ToolContext,
): Promise<string> {
  const impl = TOOL_IMPLEMENTATIONS[name];
  if (!impl) {
    return `ERROR: 不存在的工具 '${name}'。可用: ${Object.keys(TOOL_IMPLEMENTATIONS).join(", ")}`;
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let args: any;
  try {
    args = argumentsJson ? JSON.parse(argumentsJson) : {};
  } catch (e) {
    return `ERROR: 参数不是合法 JSON：${(e as Error).message}`;
  }

  try {
    return await impl(ctx, args);
  } catch (e) {
    return `ERROR: 工具执行失败：${(e as Error).message}`;
  }
}
