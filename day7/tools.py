"""
工具集（Day 7 版）
====================================
在 Day 5 的 6 个工具基础上新增：
  - web_search：调 Tavily API 做联网搜索
    Agent 只在本地笔记里搜不到时才调，避免"啥都不看先联网"。

改造点：
  execute_tool 继续用 ToolContext。web_search 是纯网络工具，不需要 ctx.client。
"""
import json
import os
from dataclasses import dataclass
from typing import Optional

import httpx

from knowledge_base import KnowledgeBase


# 全局知识库实例（Agent 启动时构造，工具函数复用）
_kb: Optional[KnowledgeBase] = None


def init_kb() -> KnowledgeBase:
    """初始化知识库（Agent 启动时调一次）"""
    global _kb
    if _kb is None:
        _kb = KnowledgeBase()
    return _kb


# ================================================================
# 工具上下文（execute_tool 时传入，供需要 LLM 的工具使用）
# ================================================================

@dataclass
class ToolContext:
    """
    执行工具时可用的外部依赖。
    对 add_tag / list_tags / search_notes 等纯本地工具没用；summarize_note 会用到 client + model。
    """
    client: object = None      # OpenAI-like client
    chat_model: str = ""       # chat completion 用的 model / endpoint id


# ================================================================
# 工具实现
# ================================================================

def tool_search_notes(ctx: ToolContext, query: str, top_k: int = 3) -> str:
    """语义检索用户笔记。返回 top_k 个最相关的片段。"""
    kb = init_kb()
    results = kb.search(query, top_k=top_k)

    if not results:
        return "未找到相关笔记内容。"

    lines = [f"检索关键词: '{query}'，找到 {len(results)} 个片段：\n"]
    for i, r in enumerate(results, 1):
        lines.append(
            f"[{i}] 来源: {r['file']}#{r['chunk_idx']}  相似度: {r['similarity']}\n"
            f"内容:\n{r['text']}\n"
        )
    return "\n".join(lines)


def tool_read_full_note(ctx: ToolContext, filename: str) -> str:
    """读整篇笔记原文（会剥掉 frontmatter）"""
    kb = init_kb()
    try:
        return kb.read_full_note(filename)
    except FileNotFoundError as e:
        try:
            available = kb.list_notes()
            return f"ERROR: {e}\n可用的笔记：{available}"
        except Exception:
            return f"ERROR: {e}"


def tool_list_notes(ctx: ToolContext) -> str:
    """列出所有笔记文件名"""
    kb = init_kb()
    notes = kb.list_notes()
    if not notes:
        return "notes/ 目录下没有笔记文件。"
    return "所有笔记文件：\n" + "\n".join(f"  - {n}" for n in notes)


def tool_add_tag(ctx: ToolContext, filename: str, tags: list) -> str:
    """给笔记添加一个或多个标签，写回 frontmatter"""
    kb = init_kb()
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        return "ERROR: tags 必须是字符串列表，例如 [\"go\", \"error-handling\"]"

    # 清洗：小写、去空格、去空
    tags = [t.strip().lower() for t in tags if t.strip()]
    if not tags:
        return "ERROR: 没有有效标签"

    try:
        meta = kb.update_meta(filename, {"tags": tags})
    except FileNotFoundError as e:
        try:
            return f"ERROR: {e}\n可用的笔记：{kb.list_notes()}"
        except Exception:
            return f"ERROR: {e}"

    return f"已给 {filename} 添加标签。当前所有标签: {meta.get('tags', [])}"


def tool_summarize_note(ctx: ToolContext, filename: str) -> str:
    """
    让 LLM 生成笔记摘要（不超过 100 字），写回 frontmatter 的 summary 字段。
    需要 ToolContext.client + chat_model。
    """
    if ctx.client is None or not ctx.chat_model:
        return "ERROR: summarize_note 需要 LLM client（工具上下文缺失）"

    kb = init_kb()
    try:
        text = kb.read_full_note(filename)
    except FileNotFoundError as e:
        try:
            return f"ERROR: {e}\n可用的笔记：{kb.list_notes()}"
        except Exception:
            return f"ERROR: {e}"

    prompt = (
        "下面是一篇笔记的原文。请用不超过 100 字的中文写一句话摘要，"
        "只写摘要正文，不要客套：\n\n"
        f"----原文----\n{text}"
    )
    try:
        resp = ctx.client.chat.completions.create(
            model=ctx.chat_model,
            messages=[
                {"role": "system", "content": "你是一个精准的摘要生成器。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        summary = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return f"ERROR: LLM 调用失败：{e}"

    if not summary:
        return "ERROR: 生成的摘要为空"

    try:
        kb.update_meta(filename, {"summary": summary})
    except Exception as e:
        return f"ERROR: 摘要生成成功但写回失败：{e}\n摘要内容: {summary}"

    return f"已为 {filename} 生成并保存摘要：\n{summary}"


def tool_list_tags(ctx: ToolContext) -> str:
    """
    列出所有笔记及其 tags/summary。
    典型用于 Agent 概览用户笔记结构。
    """
    kb = init_kb()
    notes = kb.list_notes()
    if not notes:
        return "notes/ 目录下没有笔记文件。"

    lines = [f"共 {len(notes)} 篇笔记："]
    for name in notes:
        try:
            meta = kb.read_meta(name)
        except Exception:
            meta = {}
        tags = meta.get("tags") or []
        summary = meta.get("summary") or "(无摘要)"
        tag_str = ", ".join(tags) if tags else "(无标签)"
        lines.append(f"  - {name}")
        lines.append(f"      tags: {tag_str}")
        lines.append(f"      summary: {summary}")
    return "\n".join(lines)


def tool_web_search(ctx: ToolContext, query: str, max_results: int = 3) -> str:
    """
    联网搜索（Tavily API）。仅在本地笔记里搜不到时兜底。
    需要 TAVILY_API_KEY 环境变量；没配置就明确返回错误提示，不做静默降级。
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return (
            "ERROR: 未配置 TAVILY_API_KEY。请在 .env 里加一行 "
            "`TAVILY_API_KEY=tvly-xxx`（去 tavily.com 免费申请，1000 次/月）。"
        )

    if not isinstance(query, str) or not query.strip():
        return "ERROR: query 不能为空"

    max_results = max(1, min(int(max_results or 3), 10))

    try:
        resp = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "max_results": max_results,
                "search_depth": "basic",       # basic 便宜快；advanced 才用 credit
                "include_answer": True,        # Tavily 顺手给一句 LLM 摘要
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as e:
        return f"ERROR: Tavily HTTP {e.response.status_code}: {e.response.text[:200]}"
    except Exception as e:
        return f"ERROR: Tavily 请求失败：{e}"

    results = data.get("results") or []
    if not results:
        return f"联网搜索 '{query}' 没有结果。"

    lines = [f"🌐 联网搜索: '{query}'，返回 {len(results)} 条结果："]

    answer = (data.get("answer") or "").strip()
    if answer:
        lines.append(f"\n📌 Tavily 一句话答案: {answer}\n")

    for i, r in enumerate(results, 1):
        title = (r.get("title") or "").strip()
        url = r.get("url") or ""
        content = (r.get("content") or "").strip()
        # 内容截断，防止一个结果塞爆 context
        if len(content) > 500:
            content = content[:500] + "…"
        lines.append(f"\n[{i}] {title}\n  URL: {url}\n  摘要: {content}")

    return "\n".join(lines)


# ================================================================
# 工具注册表
# ================================================================

TOOL_IMPLEMENTATIONS = {
    "search_notes": tool_search_notes,
    "read_full_note": tool_read_full_note,
    "list_notes": tool_list_notes,
    "add_tag": tool_add_tag,
    "summarize_note": tool_summarize_note,
    "list_tags": tool_list_tags,
    "web_search": tool_web_search,
}


# ================================================================
# 工具 Schema
# ================================================================

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search_notes",
            "description": (
                "语义检索用户的私人笔记，返回与查询最相关的几个片段。"
                "**每当用户问的问题涉及'我的笔记里写了什么'、需要引用笔记内容时，优先使用此工具**。"
                "支持自然语言查询，不需要关键词精确匹配。"
                "返回的每个片段包含：来源文件、chunk 位置、相似度分数、内容。"
                "如果相似度都低于 0.4，说明可能笔记里没写相关内容。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "查询问题或关键词，用自然语言即可。例如：'Go 里怎么处理错误'",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返回几个最相关的片段。默认 3。范围 1-10。",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_full_note",
            "description": (
                "读取一篇笔记的完整原文。"
                "**当 search_notes 返回的片段不够完整、或用户想要看某篇笔记的全貌时使用**。"
                "输入的是文件名（不带路径），例如 'go-tips.md'。"
                "如果文件不存在，会返回错误信息和可用文件列表。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "笔记文件名，例如 'go-tips.md'（不要带 notes/ 前缀）",
                    },
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_notes",
            "description": (
                "列出所有笔记文件的名字。"
                "**当用户问'我笔记里都有哪些内容'、或者你需要知道有哪些文件可用时使用**。"
                "不需要参数。"
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_tag",
            "description": (
                "给一篇笔记添加一个或多个标签。标签会写入笔记文件头部的 frontmatter，永久保存。"
                "**当用户说'给这篇笔记加个标签 xxx'、或你判断这篇笔记应该被打上某个分类标签时使用**。"
                "已存在的标签不会重复添加。标签会被规范化为小写。"
                "示例：add_tag(filename='go-tips.md', tags=['go', 'error-handling'])"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "笔记文件名，例如 'go-tips.md'",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要添加的标签列表，例如 ['go', 'backend']。建议用英文小写、短横线连接。",
                    },
                },
                "required": ["filename", "tags"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_note",
            "description": (
                "生成一篇笔记的一句话摘要（不超过 100 字），并保存到笔记的 frontmatter。"
                "**当用户明确要求'给 xxx 生成摘要'、'总结一下 xxx'并希望摘要被保存下来时使用**。"
                "注意：如果用户只是要看总结、不需要保存，你可以直接用 read_full_note 读全文后自己总结，不要用这个工具。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "笔记文件名，例如 'rag-notes.md'",
                    },
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tags",
            "description": (
                "列出所有笔记的标签和已保存的摘要。"
                "**当用户问'我笔记有哪些主题/分类'、或想了解笔记全景时使用**。"
                "不需要参数。返回每篇笔记的 tags 和 summary。"
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "联网搜索（Tavily）。**兜底工具**：只在本地笔记里明确没有相关内容"
                "（比如你先用 search_notes 搜过、相似度都 < 0.4，或者用户明确问的是"
                "笔记里不可能有的事，如今天的新闻、某个库的最新版本）时才使用。"
                "不要一上来就 web_search —— 用户笔记里可能有更贴合他自己上下文的答案。"
                "返回若干条网页结果（标题 / URL / 摘要），以及 Tavily 生成的一句话答案。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索查询。用自然语言，例如：'Python 3.13 有哪些新特性'",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "返回结果数量，默认 3，范围 1-10",
                    },
                },
                "required": ["query"],
            },
        },
    },
]


# ================================================================
# 统一的工具执行入口
# ================================================================

def execute_tool(name: str, arguments_json: str, ctx: Optional[ToolContext] = None) -> str:
    """
    统一工具执行入口。所有异常都会转换为字符串返回给 LLM。
    ctx: 工具上下文（含 LLM client）。可选，但 summarize_note 需要。
    """
    if name not in TOOL_IMPLEMENTATIONS:
        return f"ERROR: 不存在的工具 '{name}'。可用: {list(TOOL_IMPLEMENTATIONS.keys())}"

    try:
        args = json.loads(arguments_json) if arguments_json else {}
    except json.JSONDecodeError as e:
        return f"ERROR: 参数不是合法 JSON：{e}"

    if ctx is None:
        ctx = ToolContext()

    try:
        return TOOL_IMPLEMENTATIONS[name](ctx, **args)
    except TypeError as e:
        return f"ERROR: 参数不匹配：{e}"
    except Exception as e:
        return f"ERROR: 工具执行失败：{e}"
