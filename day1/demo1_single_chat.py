"""
Demo 1: 单轮对话
========================================
最小可运行的 LLM 调用，用来验证：
  1. 火山方舟 API Key 配置正确
  2. Endpoint 能连通
  3. OpenAI SDK 兼容层工作正常

运行：python demo1_single_chat.py
"""
import os
from openai import OpenAI
from dotenv import load_dotenv

# 从 .env 加载环境变量（API_KEY 等）
load_dotenv()

# 初始化客户端
# 火山方舟兼容 OpenAI SDK，只要换 base_url 和 key
client = OpenAI(
    api_key=os.getenv("ARK_API_KEY"),
    base_url=os.getenv("ARK_BASE_URL"),
)

# 发起对话
response = client.chat.completions.create(
    # 注意：火山方舟这里传的是 "接入点 ID"（ep-xxx），不是模型名
    model=os.getenv("ARK_ENDPOINT_ID"),
    messages=[
        # system: 给 LLM 的"身份设定"，通常放第一条
        {
            "role": "system",
            "content": "你是一个简洁友好的编程助手，回答不超过 100 字。",
        },
        # user: 用户提问
        {
            "role": "user",
            "content": "请用一句话解释什么是 Agent。",
        },
    ],
    temperature=0.7,  # 0-2，越高越"有创意"；Agent 场景一般 0.3-0.7
)

# 打印结果
# response.choices[0] 是第一个候选回复（一般也只有一个）
# .message.content 才是文本内容
print("🤖 回答：", response.choices[0].message.content)
print()
print("📊 Token 消耗：")
print(f"   输入 tokens: {response.usage.prompt_tokens}")
print(f"   输出 tokens: {response.usage.completion_tokens}")
print(f"   合计 tokens: {response.usage.total_tokens}")
