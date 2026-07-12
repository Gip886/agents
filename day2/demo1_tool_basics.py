"""
Demo 1: 观察 tool_calls 长啥样
========================================
这个 demo 不会真的执行工具，只是让你看清楚：
  1. tools schema 是什么样
  2. 当 LLM 决定用工具时，返回的消息长什么样
  3. content 什么时候是 None，什么时候有值

跑完这个再去看 demo2，你会豁然开朗。
"""
import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("ARK_API_KEY"),
    base_url=os.getenv("ARK_BASE_URL"),
)

MODEL = os.getenv("ARK_ENDPOINT_ID")

# ---------- 1. 定义工具（tools schema）----------
# 这个 schema 会以 JSON 形式发给 LLM，LLM 根据 description 决定"什么时候用哪个工具"
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取当前的日期和时间。当用户询问'现在几点''今天是几号'等实时信息时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "时区名，例如 'Asia/Shanghai'。默认为本地时区。",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取一个本地文本文件的完整内容。当用户想知道某个文件里写了什么时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件的相对路径，例如 'sample.txt' 或 'notes/todo.md'",
                    }
                },
                "required": ["path"],
            },
        },
    },
]


def call_and_inspect(user_question: str):
    """发一个问题，把 LLM 的原始返回打印出来观察"""
    print(f"\n{'=' * 60}")
    print(f"📝 用户提问：{user_question}")
    print(f"{'=' * 60}")

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "你是一个能调用工具的助手。"},
            {"role": "user", "content": user_question},
        ],
        tools=tools,  # 关键：把工具清单告诉 LLM
    )

    msg = response.choices[0].message

    print("\n🤖 LLM 返回的 assistant 消息：")
    print(f"  content     : {msg.content!r}")
    print(f"  tool_calls  : {msg.tool_calls}")

    # 如果有 tool_calls，展开看细节
    if msg.tool_calls:
        print("\n🔍 tool_calls 详情：")
        for i, tc in enumerate(msg.tool_calls, 1):
            print(f"  [{i}] id       : {tc.id}")
            print(f"      name     : {tc.function.name}")
            print(f"      arguments: {tc.function.arguments!r}")
            print(f"      ↑ 注意 arguments 是字符串（JSON string）")

            # 展示怎么解析出真正的参数
            parsed_args = json.loads(tc.function.arguments)
            print(f"      解析后    : {parsed_args}")


# ---------- 跑几个测试问题 ----------
if __name__ == "__main__":
    # 场景 1：需要用时间工具
    call_and_inspect("现在几点了？")

    # 场景 2：需要用读文件工具
    call_and_inspect("帮我看看 sample.txt 里写了啥？")

    # 场景 3：不需要工具
    call_and_inspect("你好，介绍下你自己")

    # 场景 4：可能同时需要多个工具（观察 LLM 会不会一次要求多个）
    call_and_inspect("请告诉我现在的时间，同时读一下 sample.txt 的内容")

    print("\n" + "=" * 60)
    print("✅ 观察完成！你应该注意到：")
    print("  1. 需要工具时，content=None，tool_calls 有值")
    print("  2. 不需要工具时，content 有文本，tool_calls=None")
    print("  3. arguments 是 JSON 字符串，用之前要 json.loads()")
    print("  4. 每个 tool_call 有唯一 id，稍后 tool 结果要通过它匹配")
    print("=" * 60)
