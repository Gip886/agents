"""
Demo 2: 多轮对话 + Streaming + Token 统计
========================================
这是 Agent 的雏形。核心概念：
  1. messages 数组 = Agent 的"短期记忆"
  2. 每轮把 user 和 assistant 都追加进去，LLM 才能"记住"上下文
  3. stream=True 让 LLM 一个字一个字吐出来，体验更好
  4. stream_options.include_usage 让最后一个 chunk 带上 token 消耗

命令：
  你: <任何问题>       → 正常对话
  你: clear            → 清空历史（保留 system prompt）
  你: exit             → 退出
"""
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("ARK_API_KEY"),
    base_url=os.getenv("ARK_BASE_URL"),
)

MODEL = os.getenv("ARK_ENDPOINT_ID")

# ---------- 对话状态 ----------
# messages 是 Agent 的"记忆"，每一轮都要把 user + assistant 加进来
messages = [
    {
        "role": "system",
        "content": "你是一个耐心的编程导师，擅长 Python 和 Go。回答简洁，善用类比。",
    },
]

# 累计 token（跨轮）
total_prompt_tokens = 0
total_completion_tokens = 0

print("💬 开始对话（输入 'exit' 退出，'clear' 清空历史）")
print("=" * 50)

while True:
    # 1. 拿用户输入
    try:
        user_input = input("\n你: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n👋 再见！")
        break

    if user_input.lower() == "exit":
        print("👋 再见！")
        break
    if user_input.lower() == "clear":
        messages = messages[:1]  # 保留 system prompt
        print("🧹 历史已清空\n")
        continue
    if not user_input:
        continue

    # 2. 把用户消息加进历史
    messages.append({"role": "user", "content": user_input})

    # 3. 调用 LLM，流式返回
    stream = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        stream=True,
        # 关键：让 stream 也返回 usage（默认 stream 不带 usage）
        stream_options={"include_usage": True},
    )

    # 4. 边收边打印，同时拼接完整回复
    print("🤖 助手: ", end="", flush=True)
    full_reply = ""
    turn_usage = None

    for chunk in stream:
        # chunk.choices 可能为空（最后一个带 usage 的 chunk 通常没有 choices）
        if chunk.choices:
            delta = chunk.choices[0].delta.content
            if delta:
                print(delta, end="", flush=True)
                full_reply += delta

        # usage 只在最后一个 chunk 里出现
        if chunk.usage:
            turn_usage = chunk.usage

    print()  # 换行

    # 5. 把 LLM 的回复也加进历史（下一轮它才"记得"）
    messages.append({"role": "assistant", "content": full_reply})

    # 6. Token 统计
    if turn_usage:
        total_prompt_tokens += turn_usage.prompt_tokens
        total_completion_tokens += turn_usage.completion_tokens
        print(
            f"\n📊 本轮：输入 {turn_usage.prompt_tokens} + 输出 {turn_usage.completion_tokens} "
            f"= {turn_usage.total_tokens} tokens"
        )
        print(
            f"📈 累计：输入 {total_prompt_tokens} + 输出 {total_completion_tokens} "
            f"= {total_prompt_tokens + total_completion_tokens} tokens"
        )
        print(f"💾 当前对话历史：{len(messages)} 条消息")
