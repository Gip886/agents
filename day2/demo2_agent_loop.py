"""
Demo 2: 完整的 Agent Loop
========================================
今天的重点。这是一个能真正"做事"的 Agent：
  - 会自己决定什么时候用工具
  - 会执行工具，把结果告诉 LLM
  - 会连续调用多个工具直到任务完成

核心是一个 while 循环，直到 LLM 不再要求调用工具为止。

命令：
  你: 现在几点？
  你: 帮我读一下 sample.txt
  你: 帮我读一下 sample.txt，然后告诉我现在几点。
  你: exit
"""
import json
import os
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("ARK_API_KEY"),
    base_url=os.getenv("ARK_BASE_URL"),
)

MODEL = os.getenv("ARK_ENDPOINT_ID")

# ================================================================
# 一、工具的两面：schema（给 LLM 看）+ 实现（给 Python 跑）
# ================================================================

# ---- 工具 1：查当前时间 ----
def get_current_time(timezone: str = "Asia/Shanghai") -> str:
    """真实的 Python 实现。timezone 参数暂时不处理，简化。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---- 工具 2：读文件 ----
def read_file(path: str) -> str:
    """读本地文件。注意 try/except：错误也要作为字符串返回给 LLM，让它自己判断。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        # 太长就截断，避免塞爆 context
        if len(content) > 2000:
            content = content[:2000] + f"\n\n[...文件太长已截断，总长 {len(content)} 字符]"
        return content
    except FileNotFoundError:
        return f"ERROR: 文件不存在：{path}"
    except Exception as e:
        return f"ERROR: 读取文件失败：{e}"


# ---- 工具注册表：名字 -> 函数 ----
TOOL_IMPLEMENTATIONS = {
    "get_current_time": get_current_time,
    "read_file": read_file,
}


# ---- 工具 schema：告诉 LLM 有哪些工具 ----
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取当前的日期和时间。当用户询问'现在几点''今天几号'等实时信息时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "时区，例如 'Asia/Shanghai'。默认为 Asia/Shanghai。",
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
            "description": (
                "读取一个本地文本文件的完整内容。"
                "当用户想知道某个文件里写了什么、想让你分析文件内容时使用。"
                "返回文件的完整内容，或以 'ERROR:' 开头的错误信息。"
            ),
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


# ================================================================
# 二、Agent 核心：tool-calling loop
# ================================================================

def execute_tool(name: str, arguments_json: str) -> str:
    """
    执行工具的统一入口。
    - 处理 JSON 解析
    - 处理未知工具（LLM 可能幻觉调用不存在的工具）
    - 处理执行异常
    所有情况都返回字符串给 LLM，绝不抛异常。
    """
    print(f"  🔧 执行工具：{name}({arguments_json})")

    # 1. 检查工具是否存在
    if name not in TOOL_IMPLEMENTATIONS:
        result = f"ERROR: 不存在的工具 '{name}'。可用工具：{list(TOOL_IMPLEMENTATIONS.keys())}"
        print(f"  ← {result}")
        return result

    # 2. 解析参数
    try:
        args = json.loads(arguments_json) if arguments_json else {}
    except json.JSONDecodeError as e:
        return f"ERROR: 参数不是合法 JSON：{e}"

    # 3. 执行
    try:
        result = TOOL_IMPLEMENTATIONS[name](**args)
    except Exception as e:
        result = f"ERROR: 工具执行失败：{e}"

    # 简单打印结果（长了截断）
    preview = str(result)
    if len(preview) > 200:
        preview = preview[:200] + "..."
    print(f"  ← {preview}")
    return str(result)


def run_agent(user_input: str, messages: list, max_rounds: int = 10) -> str:
    """
    Agent 主循环。返回最终回答。
    messages 会被就地修改（追加本轮所有消息）。
    """
    # 1. 把用户消息加进历史
    messages.append({"role": "user", "content": user_input})

    # 2. Loop：直到 LLM 不再要求调用工具
    for round_num in range(1, max_rounds + 1):
        print(f"\n  ─ 第 {round_num} 轮 LLM 调用 ─")

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS_SCHEMA,
        )

        msg = response.choices[0].message

        # 3. ⚠️ 关键：把 assistant 消息加进历史（无论有没有 tool_calls）
        #    如果这里忘了，下一轮 LLM 会说"我没有调过工具"
        #    OpenAI SDK 的对象可以直接用 model_dump() 转 dict
        messages.append(msg.model_dump(exclude_none=True))

        # 4. 如果没有 tool_calls，说明 LLM 给出了最终答案
        if not msg.tool_calls:
            return msg.content or "(无回复)"

        # 5. 有 tool_calls：逐个执行
        for tool_call in msg.tool_calls:
            result = execute_tool(
                tool_call.function.name,
                tool_call.function.arguments,
            )
            # ⚠️ tool_call_id 必须！LLM 靠它匹配"这是哪次调用的结果"
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

        # 6. 回到循环开头，让 LLM 拿着 tool 结果继续

    return f"⚠️ 超过最大轮次 {max_rounds}，Agent 可能陷入了循环"


# ================================================================
# 三、交互入口
# ================================================================

if __name__ == "__main__":
    messages = [
        {
            "role": "system",
            "content": (
                "你是一个能调用工具的助手。你有两个工具：get_current_time 和 read_file。"
                "根据用户的问题，判断是否需要调用工具。可以连续调用多次。"
            ),
        }
    ]

    print("🤖 Agent 已就绪（输入 'exit' 退出，'clear' 清空历史）")
    print("=" * 60)

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
            messages = messages[:1]
            print("🧹 历史已清空")
            continue
        if not user_input:
            continue

        answer = run_agent(user_input, messages)
        print(f"\n🤖 最终回答：{answer}")
        print(f"\n💾 当前对话历史：{len(messages)} 条消息")
