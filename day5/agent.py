"""
知识助手 Agent v2（Day 5：加记忆管理 + 打标签/摘要工具）
====================================
相比 Day 4 的改动：
  1. messages list → ConversationMemory：超阈值自动 LLM 摘要压缩
  2. 3 个新工具：add_tag / summarize_note / list_tags
  3. 每轮结束后打印压缩事件（如果发生了）

跑法：
    python agent.py

先跑 python ingest.py 建库！
"""
import os

from openai import OpenAI
from dotenv import load_dotenv

from tools import TOOLS_SCHEMA, execute_tool, init_kb, ToolContext
from memory import ConversationMemory, make_llm_summarizer

load_dotenv()

client = OpenAI(
    api_key=os.getenv("ARK_API_KEY"),
    base_url=os.getenv("ARK_BASE_URL"),
)
CHAT_MODEL = os.getenv("ARK_ENDPOINT_ID")

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


def run_agent_turn(user_input: str, memory: ConversationMemory, tool_ctx: ToolContext, max_rounds: int = MAX_ROUNDS) -> tuple[str, dict]:
    """
    跑一轮 Agent 对话。返回 (最终回答, 统计信息)。
    memory 会被就地修改（追加本轮所有消息）。
    """
    memory.append({"role": "user", "content": user_input})

    stats = {
        "llm_rounds": 0,
        "tool_calls": 0,
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
    }

    for round_num in range(1, max_rounds + 1):
        stats["llm_rounds"] = round_num
        print(f"\n  ─ 第 {round_num} 轮 ─")

        response = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=memory.get_messages(),
            tools=TOOLS_SCHEMA,
        )

        if response.usage:
            stats["total_prompt_tokens"] += response.usage.prompt_tokens
            stats["total_completion_tokens"] += response.usage.completion_tokens

        msg = response.choices[0].message

        # 把 assistant 消息加进历史
        memory.append(msg)

        # 没有 tool_calls：LLM 给出了最终答案
        if not msg.tool_calls:
            print("  🤔 LLM 综合信息，给出回答")
            return msg.content or "(无回复)", stats

        # 有 tool_calls：执行并回传
        print(f"  🤔 LLM 决定调用 {len(msg.tool_calls)} 个工具")
        for tool_call in msg.tool_calls:
            name = tool_call.function.name
            args = tool_call.function.arguments

            print(f"  🔧 {name}({args})")
            result = execute_tool(name, args, ctx=tool_ctx)
            stats["tool_calls"] += 1

            preview = result[:200].replace("\n", " ")
            print(f"     ↳ {preview}{'...' if len(result) > 200 else ''}")

            memory.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

    return f"⚠️ 超过最大轮次 {max_rounds}，可能陷入循环", stats


def main():
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

    # ConversationMemory：把 client + model 传给摘要函数
    memory = ConversationMemory(
        system_prompt=SYSTEM_PROMPT,
        summarize_fn=make_llm_summarizer(client, CHAT_MODEL),
    )
    tool_ctx = ToolContext(client=client, chat_model=CHAT_MODEL)

    print("\n" + "=" * 60)
    print("🤖 知识助手 v2 已启动（Day 5：加了记忆压缩 + 打标签/摘要）")
    print("   输入 'exit' 退出，'clear' 清空对话历史，'mem' 查看记忆状态")
    print("=" * 60)

    session_prompt_tokens = 0
    session_completion_tokens = 0

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
            memory.clear()
            print("🧹 对话历史已清空")
            continue
        if user_input.lower() == "mem":
            msgs = memory.get_messages()
            print(f"💾 当前 {len(msgs)} 条消息，约 {memory.total_chars()} 字符（阈值 {memory.trigger_chars}）")
            continue
        if not user_input:
            continue

        answer, stats = run_agent_turn(user_input, memory, tool_ctx)

        session_prompt_tokens += stats["total_prompt_tokens"]
        session_completion_tokens += stats["total_completion_tokens"]

        print(f"\n🤖 {answer}")
        print(
            f"\n📊 本次任务：{stats['llm_rounds']} 轮 LLM 调用 | "
            f"{stats['tool_calls']} 次工具调用 | "
            f"消耗 {stats['total_prompt_tokens'] + stats['total_completion_tokens']} tokens"
        )
        print(
            f"💾 对话历史：{len(memory.get_messages())} 条 / {memory.total_chars()} 字符 | "
            f"累计 tokens: {session_prompt_tokens + session_completion_tokens}"
        )

        # 尝试压缩
        event = memory.maybe_compress()
        if event:
            print(
                f"🧠 [记忆压缩] {event['before_msgs']} 条 / {event['before_chars']} 字符"
                f" → {event['after_msgs']} 条 / {event['after_chars']} 字符"
            )
            print(f"   摘要预览: {event['summary_preview']}")


if __name__ == "__main__":
    main()
