"""
知识助手 Agent v3（Day 6：抽出 KnowledgeAgent 类）
====================================
相比 Day 5 的关键改动：
  把"Agent 引擎"和"CLI 交互"彻底分离。
  - KnowledgeAgent 类：只关心业务（LLM 调用、tool 执行、记忆管理）
  - run_turn() 返回结构化 Trace：CLI 和 Streamlit 各自决定怎么渲染
  - CLI 模式（main）保留，UI 模式（app.py）复用同一个 Agent 类

跑法：
  python agent.py       # CLI 模式（同 Day 5）
  streamlit run app.py  # Web UI 模式（Day 6 新增）

先跑 python ingest.py 建库！
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from openai import OpenAI
from dotenv import load_dotenv

from tools import TOOLS_SCHEMA, execute_tool, init_kb, ToolContext
from memory import ConversationMemory, make_llm_summarizer

load_dotenv()


MAX_ROUNDS = 8   # 单次任务最大 LLM 轮次，防死循环


SYSTEM_PROMPT = """你是一个基于用户私人笔记的知识助手。用户会问你问题，你有以下工具：

【只读工具】
- search_notes(query, top_k)：语义检索笔记，返回相关片段
- read_full_note(filename)：读一篇笔记的完整原文
- list_notes()：列出所有笔记文件名
- list_tags()：列出所有笔记的标签和已保存的摘要（概览用）

【写入工具】—— 会修改笔记文件
- add_tag(filename, tags)：给笔记加标签（写回 frontmatter）
- summarize_note(filename)：让 LLM 生成摘要并保存到笔记 frontmatter

工作原则：

1. **优先使用工具查笔记，不要凭记忆回答**。用户问的每个具体问题，都应该先 search_notes。
2. **如果 search_notes 结果的相似度都 < 0.4，明确告诉用户"我在你的笔记里没找到相关内容"**。不要瞎编。
3. **回答时要引用来源**：用 `[来源: xxx.md]` 或 `[来源: xxx.md#N]` 的格式。
4. **一次可以并行调用多个工具**以提高效率。
5. **如果第一次 search 结果不理想，可以换个关键词再 search 一次**。但不要重复超过 2 次。
6. **写入工具要谨慎**：只有用户明确说"加标签"、"保存摘要"时才调用 add_tag / summarize_note。仅仅想看总结时用 read_full_note 自己总结即可。
7. 简单闲聊、通用问题（不涉及用户笔记）不需要用工具。

回答风格：简洁、准确、有引用。中文回答。"""


# ================================================================
# 结构化 Trace —— UI 和 CLI 都消费这个
# ================================================================

@dataclass
class ToolCallTrace:
    """一次工具调用的完整记录"""
    name: str
    arguments: str          # JSON 字符串
    result: str             # 工具返回值


@dataclass
class RoundTrace:
    """一轮 LLM 调用的完整记录"""
    round_num: int
    tool_calls: list[ToolCallTrace] = field(default_factory=list)
    assistant_text: str = ""   # 如果这轮 LLM 给出了最终文本回答
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class TurnResult:
    """一次用户提问（可能包含多轮 LLM）的完整结果"""
    answer: str
    rounds: list[RoundTrace]
    compression_event: dict | None = None   # 本轮结束触发的压缩事件

    @property
    def total_tool_calls(self) -> int:
        return sum(len(r.tool_calls) for r in self.rounds)

    @property
    def total_tokens(self) -> int:
        return sum(r.prompt_tokens + r.completion_tokens for r in self.rounds)


# ================================================================
# KnowledgeAgent —— Day 6 的核心抽象
# ================================================================

class KnowledgeAgent:
    """
    知识助手 Agent 引擎。业务逻辑完全从 UI 里拆出来，方便 CLI 和 Streamlit 复用。

    典型用法：
        agent = KnowledgeAgent()
        result = agent.run_turn("我笔记里 Go 错误处理是怎么讲的？")
        print(result.answer)
        for round_trace in result.rounds:
            for tc in round_trace.tool_calls:
                print(f"  🔧 {tc.name}({tc.arguments}) → {tc.result[:100]}")
    """

    def __init__(
        self,
        system_prompt: str = SYSTEM_PROMPT,
        max_rounds: int = MAX_ROUNDS,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.client = OpenAI(
            api_key=api_key or os.getenv("ARK_API_KEY"),
            base_url=base_url or os.getenv("ARK_BASE_URL"),
        )
        self.model = model or os.getenv("ARK_ENDPOINT_ID")
        self.max_rounds = max_rounds

        self.memory = ConversationMemory(
            system_prompt=system_prompt,
            summarize_fn=make_llm_summarizer(self.client, self.model),
        )
        self.tool_ctx = ToolContext(client=self.client, chat_model=self.model)

    # ---------- 供 UI 调用的辅助 ----------

    def clear_memory(self):
        self.memory.clear()

    def memory_stats(self) -> dict:
        msgs = self.memory.get_messages()
        return {
            "n_messages": len(msgs),
            "chars": self.memory.total_chars(),
            "trigger_chars": self.memory.trigger_chars,
        }

    # ---------- 核心：跑一轮用户对话 ----------

    def run_turn(self, user_input: str) -> TurnResult:
        """
        跑一次用户提问的完整流程（可能包含多轮 LLM + 工具调用）。
        返回结构化 TurnResult 供 UI/CLI 各自消费。
        """
        self.memory.append({"role": "user", "content": user_input})

        rounds: list[RoundTrace] = []

        for round_num in range(1, self.max_rounds + 1):
            round_trace = RoundTrace(round_num=round_num)

            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.memory.get_messages(),
                tools=TOOLS_SCHEMA,
            )

            if response.usage:
                round_trace.prompt_tokens = response.usage.prompt_tokens
                round_trace.completion_tokens = response.usage.completion_tokens

            msg = response.choices[0].message
            self.memory.append(msg)

            # 没有 tool_calls：LLM 给出了最终答案，本次任务结束
            if not msg.tool_calls:
                round_trace.assistant_text = msg.content or "(无回复)"
                rounds.append(round_trace)
                compression = self.memory.maybe_compress()
                return TurnResult(
                    answer=round_trace.assistant_text,
                    rounds=rounds,
                    compression_event=compression,
                )

            # 有 tool_calls：执行并回传
            for tool_call in msg.tool_calls:
                name = tool_call.function.name
                args = tool_call.function.arguments
                result = execute_tool(name, args, ctx=self.tool_ctx)

                round_trace.tool_calls.append(ToolCallTrace(
                    name=name, arguments=args, result=result,
                ))

                self.memory.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

            rounds.append(round_trace)

        # 走完最大轮次还没结束
        compression = self.memory.maybe_compress()
        return TurnResult(
            answer=f"⚠️ 超过最大轮次 {self.max_rounds}，可能陷入循环",
            rounds=rounds,
            compression_event=compression,
        )


# ================================================================
# CLI 入口（保留 Day 5 的交互）
# ================================================================

def _print_turn(result: TurnResult):
    """把 TurnResult 打印成 Day 5 那样的思考轨迹"""
    for r in result.rounds:
        print(f"\n  ─ 第 {r.round_num} 轮 ─")
        if r.tool_calls:
            print(f"  🤔 LLM 决定调用 {len(r.tool_calls)} 个工具")
            for tc in r.tool_calls:
                print(f"  🔧 {tc.name}({tc.arguments})")
                preview = tc.result[:200].replace("\n", " ")
                print(f"     ↳ {preview}{'...' if len(tc.result) > 200 else ''}")
        else:
            print("  🤔 LLM 综合信息，给出回答")


def main():
    agent = KnowledgeAgent()

    kb = init_kb()
    n = kb.collection.count()
    if n == 0:
        print("❌ 知识库为空！请先跑：python ingest.py")
        return
    print(f"✅ 知识库就绪：{n} 个 chunk")

    notes = kb.list_notes()
    print(f"📚 可用笔记（{len(notes)}）：")
    for nm in notes:
        print(f"   - {nm}")

    print("\n" + "=" * 60)
    print("🤖 知识助手 v3 已启动（Day 6：CLI 模式；也可用 streamlit run app.py）")
    print("   输入 'exit' 退出，'clear' 清空对话历史，'mem' 查看记忆状态")
    print("=" * 60)

    session_tokens = 0

    while True:
        try:
            user_input = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 再见！")
            break

        if user_input.lower() == "exit":
            print("👋 再见！")
            break
        if user_input.lower() == "clear":
            agent.clear_memory()
            print("🧹 对话历史已清空")
            continue
        if user_input.lower() == "mem":
            s = agent.memory_stats()
            print(f"💾 当前 {s['n_messages']} 条消息，约 {s['chars']} 字符（阈值 {s['trigger_chars']}）")
            continue
        if not user_input:
            continue

        result = agent.run_turn(user_input)
        _print_turn(result)
        session_tokens += result.total_tokens

        print(f"\n🤖 {result.answer}")
        print(
            f"\n📊 本次任务：{len(result.rounds)} 轮 LLM 调用 | "
            f"{result.total_tool_calls} 次工具调用 | "
            f"消耗 {result.total_tokens} tokens"
        )
        s = agent.memory_stats()
        print(f"💾 对话历史：{s['n_messages']} 条 / {s['chars']} 字符 | 累计: {session_tokens}")

        if result.compression_event:
            e = result.compression_event
            print(f"🧠 [记忆压缩] {e['before_msgs']} 条 / {e['before_chars']} 字符"
                  f" → {e['after_msgs']} 条 / {e['after_chars']} 字符")
            print(f"   摘要预览: {e['summary_preview']}")


if __name__ == "__main__":
    main()
