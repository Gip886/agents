"""
工具集：给 Agent 调用的函数 + Schema
====================================
每个工具两面：
  - schema：给 LLM 看的"接口文档"
  - 实现：Python 函数

Tool description 写作原则：
  1. 清楚说明"什么时候用"（使用场景）
  2. 参数示例
  3. 返回值格式
"""
import json
from typing import Optional

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
# 工具实现
# ================================================================

def tool_search_notes(query: str, top_k: int = 3) -> str:
    """
    语义检索用户笔记。返回 top_k 个最相关的片段。
    """
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


def tool_read_full_note(filename: str) -> str:
    """
    读整篇笔记原文。
    """
    kb = init_kb()
    try:
        return kb.read_full_note(filename)
    except FileNotFoundError as e:
        # 返回错误消息给 LLM，让它自己判断怎么办
        try:
            available = kb.list_notes()
            return f"ERROR: {e}\n可用的笔记：{available}"
        except Exception:
            return f"ERROR: {e}"


def tool_list_notes() -> str:
    """
    列出所有笔记文件名。
    """
    kb = init_kb()
    notes = kb.list_notes()
    if not notes:
        return "notes/ 目录下没有笔记文件。"
    return "所有笔记文件：\n" + "\n".join(f"  - {n}" for n in notes)


# ================================================================
# 工具注册表（名字 → 函数）
# ================================================================

TOOL_IMPLEMENTATIONS = {
    "search_notes": tool_search_notes,
    "read_full_note": tool_read_full_note,
    "list_notes": tool_list_notes,
}


# ================================================================
# 工具 Schema（给 LLM 看的"接口文档"）
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
]


# ================================================================
# 统一的工具执行入口（给 agent.py 调用）
# ================================================================

def execute_tool(name: str, arguments_json: str) -> str:
    """
    统一工具执行入口。所有异常都会转换为字符串返回给 LLM。
    """
    if name not in TOOL_IMPLEMENTATIONS:
        return f"ERROR: 不存在的工具 '{name}'。可用: {list(TOOL_IMPLEMENTATIONS.keys())}"

    try:
        args = json.loads(arguments_json) if arguments_json else {}
    except json.JSONDecodeError as e:
        return f"ERROR: 参数不是合法 JSON：{e}"

    try:
        return TOOL_IMPLEMENTATIONS[name](**args)
    except TypeError as e:
        return f"ERROR: 参数不匹配：{e}"
    except Exception as e:
        return f"ERROR: 工具执行失败：{e}"
