# 🤖 Agent 系统学习 & 项目实践规划

> 一份为 Java/Go 后端开发者定制的 Agent 入门路线
> 时间：一周 · 语言：Python · LLM：火山方舟 Doubao
> 项目：个人知识管理助手

## 🌐 在线文档站

> **[👉 打开学习站点（GitHub Pages）](https://gip886.github.io/agents/)**
>
> 包含每日详细教程、代码示例、进度总览。

## 📊 学习进度

| Day | 主题 | 状态 | 详细 |
|-----|------|------|------|
| 1 | 环境搭建 + LLM 首次调用 | ✅ 完成 | [教程](https://gip886.github.io/agents/day1.html) · [代码](./day1/) |
| 2 | Tool Use 工具调用 | ✅ 完成 | [教程](https://gip886.github.io/agents/day2.html) · [代码](./day2/) |
| 3 | RAG 向量检索 | ✅ 完成 | [教程](https://gip886.github.io/agents/day3.html) · [代码](./day3/) |
| 4 | 知识助手 v1 组装 | ✅ 完成 | [教程](https://gip886.github.io/agents/day4.html) · [代码](./day4/) |
| 5 | 记忆增强 | ✅ 完成 | [教程](https://gip886.github.io/agents/day5.html) · [代码](./day5/) |
| 6 | Streamlit Web UI | ✅ 完成 | [教程](https://gip886.github.io/agents/day6.html) · [代码](./day6/) |
| 7 | ReAct + 联网兜底 + 复盘 | ✅ 完成 | [教程](https://gip886.github.io/agents/day7.html) · [代码](./day7/) · [复盘](./day7/REVIEW.md) |

## 🌍 进阶：Web 全栈版

Day 1-7 的 Python 手写版之后，另外做了一版 **Next.js + TypeScript** 全栈实现，同一份能力换栈重写，方便和现有前端项目整合、可上 Vercel：

| 版本 | 目录 | 前端 | 向量库 | 部署 |
|---|---|---|---|---|
| Python 教学版 | `day1/` … `day7/` | Streamlit | ChromaDB | 本地 |
| Web 全栈版 | [`agents-web/`](./agents-web/) | Next.js + React | SQLite + 手写 cosine | Vercel-ready |

Web 版支持：**流式对话（SSE）** · **7 个 Tool** · **对话记忆自动压缩** · **ReAct Thought 显式化** · **本地 + 联网兜底**。详见 [`agents-web/README.md`](./agents-web/README.md)。

## 📂 仓库结构

```
agents/
├── README.md          # 本文件（项目总览）
├── docs/              # GitHub Pages 网站源码
│   ├── index.html     # 网站首页
│   ├── plan.html      # 总体计划
│   ├── day1.html      # Day 1 详细教程
│   ├── streaming-notes.md  # 流式对话设计笔记
│   └── assets/        # 共享 CSS
├── day1/              # Day 1 代码（Python）
│   ├── README.md      # Day 1 快速参考
│   ├── .env.example   # 环境变量模板
│   ├── requirements.txt
│   └── demo1_*.py     # 示例代码
├── dayN/              # 后续每天一个目录（Python）
└── agents-web/        # Next.js + TypeScript 全栈版
    ├── src/lib/       # Agent / tools / kb / memory / embedding
    ├── src/app/       # Next.js App Router (page + api routes)
    └── README.md      # Web 版说明
```

---

## 📖 目录

- [整体规划](#整体规划)
- [技术选型](#技术选型)
- [一周详细计划](#一周详细计划)
  - [Day 1 · 环境搭建 + LLM 首次调用](#day-1--环境搭建--llm-首次调用)
  - [Day 2 · Tool Use（工具调用）](#day-2--tool-use工具调用)
  - [Day 3 · RAG 核心：向量检索](#day-3--rag-核心向量检索)
  - [Day 4 · 组装：知识助手 v1](#day-4--组装知识助手-v1)
  - [Day 5 · 增强：记忆 + 多轮](#day-5--增强记忆--多轮)
  - [Day 6 · 打磨 + Web UI](#day-6--打磨--web-ui)
  - [Day 7 · 复盘 + 进阶方向](#day-7--复盘--进阶方向)
- [进阶项目方向](#进阶项目方向)
- [常见问题速查](#常见问题速查)

---

## 整体规划

学习路径分四个阶段，我们的一周计划聚焦在**阶段二 + 阶段四**（跳过纯理论，边做边学）：

### 阶段一：基础认知
- **核心概念**：Agent = LLM + 记忆 + 工具 + 规划
- **经典架构**：ReAct（Reason + Act）、Plan-and-Execute、Reflexion
- **必读**：
  - [Lilian Weng - LLM Powered Autonomous Agents](https://lilianweng.github.io/posts/2023-06-23-agent/)
  - [Anthropic - Building effective agents](https://www.anthropic.com/research/building-effective-agents)（强烈推荐）

### 阶段二：核心技术模块

| 模块 | 关键内容 | Demo 建议 |
|------|---------|-----------|
| **1. Tool Use** | 工具定义 schema、并行调用、错误处理 | 让 Agent 调用天气 API + 计算器 |
| **2. Prompt 工程** | System prompt 设计、Few-shot、CoT | 对比不同 prompt 的表现 |
| **3. Memory** | 短期（对话历史）、长期（向量库）、上下文压缩 | 用 SQLite/Chroma 做记事本 Agent |
| **4. RAG** | 切分、embedding、检索、rerank | 做"读 PDF 问答" Agent |
| **5. Planning & Loop** | ReAct 循环、任务拆解、状态机 | 手写 ReAct loop |

⚠️ **先手写一遍 Agent loop，再用框架**，否则会停留在"调 API"层面。

### 阶段三：框架 & 生态（选 1-2 个）

- **Claude Agent SDK**（官方，工程化最好）
- **LangGraph**（图结构编排）
- **CrewAI / AutoGen**（多 Agent 协作）
- **MCP (Model Context Protocol)**：Agent 生态的"USB 接口"

### 阶段四：项目实践

**本周项目：个人知识管理助手** 🌟
- 功能：读入 Markdown / PDF / 网页，回答问题、生成摘要、自动打标签
- 涉及：RAG + Tool Use + Memory

---

## 技术选型

| 项 | 选择 | 理由 |
|---|------|------|
| **语言** | Python | Agent 生态 90% 在 Python |
| **LLM** | 火山方舟 Doubao-1.5-pro | 兼容 OpenAI SDK，切换零成本 |
| **Embedding** | 火山方舟 Doubao-embedding | 同平台，省事 |
| **向量库** | ChromaDB | 本地文件，零部署 |
| **框架** | 第一版手写，第二版用 LangChain | 手写才能真懂原理 |
| **UI** | Streamlit | 10 行代码起一个网页 |

---

## 一周详细计划

### Day 1 · 环境搭建 + LLM 首次调用

**目标**：跑通火山引擎 API，理解 messages 结构

#### 任务清单
- [ ] 环境准备（15 分钟）
- [ ] 火山方舟开通 + 拿 API Key（10 分钟）
- [ ] Demo 1 — 单轮对话（30 分钟）
- [ ] Demo 2 — 多轮对话 + Streaming（40 分钟）
- [ ] 小挑战：打印 token 消耗（选做）

#### Step 1: 环境准备

```bash
# 检查 Python 版本，需要 3.10+
python3 --version

# 创建项目目录
mkdir -p ~/Documents/practice/agents/day1
cd ~/Documents/practice/agents/day1

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install openai python-dotenv
```

> 💡 **给 Java/Go 背景的类比**：
> - `venv` ≈ Go 的 `go.mod` 项目隔离 / Java 的 Maven 项目
> - `pip install` ≈ `go get` / Maven 加依赖
> - 每次新开终端要 `source venv/bin/activate`

#### Step 2: 火山方舟开通

1. 访问 [火山方舟控制台](https://console.volcengine.com/ark)
2. 左侧菜单 **"在线推理"** → **"创建推理接入点"**
3. 选择模型：**Doubao-1.5-pro-32k**（推荐）
4. 拿到接入点 ID：`ep-2024xxxx-xxxxx`
5. **"API Key 管理"** → 创建 API Key

#### Step 3: 创建 `.env`

```
ARK_API_KEY=你的APIKey
ARK_ENDPOINT_ID=你的接入点ID
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
```

#### Step 4: Demo 1 - 单轮对话

`demo1_single_chat.py`:

```python
"""Demo 1: 单轮对话"""
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("ARK_API_KEY"),
    base_url=os.getenv("ARK_BASE_URL"),
)

response = client.chat.completions.create(
    model=os.getenv("ARK_ENDPOINT_ID"),
    messages=[
        {"role": "system", "content": "你是一个简洁友好的编程助手，回答不超过 100 字。"},
        {"role": "user", "content": "请用一句话解释什么是 Agent。"},
    ],
)

print("🤖 回答：", response.choices[0].message.content)
print("\n📊 Token 消耗：", response.usage)
```

运行：`python demo1_single_chat.py`

#### Step 5: Demo 2 - 多轮对话 + Streaming

`demo2_chat_loop.py`:

```python
"""Demo 2: 多轮对话 + Streaming"""
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("ARK_API_KEY"),
    base_url=os.getenv("ARK_BASE_URL"),
)

messages = [
    {"role": "system", "content": "你是一个耐心的编程导师，擅长 Python 和 Go。"},
]

print("💬 开始对话（输入 'exit' 退出，'clear' 清空历史）\n")

while True:
    user_input = input("你: ").strip()
    if user_input.lower() == "exit":
        print("👋 再见！")
        break
    if user_input.lower() == "clear":
        messages = messages[:1]
        print("🧹 历史已清空\n")
        continue
    if not user_input:
        continue

    messages.append({"role": "user", "content": user_input})

    stream = client.chat.completions.create(
        model=os.getenv("ARK_ENDPOINT_ID"),
        messages=messages,
        stream=True,
    )

    print("🤖 助手: ", end="", flush=True)
    full_reply = ""
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            print(delta, end="", flush=True)
            full_reply += delta
    print("\n")

    messages.append({"role": "assistant", "content": full_reply})
```

#### 今日核心概念

| 概念 | 一句话解释 |
|------|-----------|
| **messages 数组** | Agent 的记忆载体，`[{role, content}, ...]` |
| **system prompt** | 给 LLM 的"身份设定"，放第一条 |
| **stream=True** | 流式返回，改善体验 |
| **temperature** | 0-2，Agent 场景一般 0.3-0.7 |

#### 验收标准
- ✅ 解释为什么第二轮对话 LLM 能"记住"第一轮内容
- ✅ 说出 system / user / assistant 三个 role 的作用
- ✅ 两个 demo 都能跑通

---

### Day 2 · Tool Use（工具调用）

**目标**：让 LLM 会"用工具"，这是 Agent 最关键的一步

#### 任务清单
- [ ] 学 Tool Use / Function Calling 的 JSON schema
- [ ] Demo 3：写 2 个工具函数
  - `get_current_time()` 返回当前时间
  - `read_file(path)` 读本地文件内容
- [ ] 实现完整的 tool-calling loop：
  - LLM 决定调用 → 你执行 → 结果回传 → LLM 继续

**产出**：`agent_with_tools.py`，用户问"帮我读一下 notes.md 讲了啥"，Agent 会自动调用 `read_file`

⚠️ **重点**：亲手写这个 while loop，理解 `tool_calls` → `tool_result` 的循环，这是 Agent 的心脏

---

### Day 3 · RAG 核心：向量检索

**目标**：把文档"塞进"LLM 的能力

#### 任务清单
- [ ] 理解概念：chunking、embedding、余弦相似度、top-k
- [ ] Demo 4 - `ingest.py`：
  1. 读一个 Markdown 文件
  2. 按段落切分（每 500 字一块）
  3. 调豆包 embedding 生成向量
  4. 存进 ChromaDB
- [ ] Demo 5 - `query.py`：给一句问题 → embedding → 检索 top 3 → 打印

**产出**：能在自己笔记上做语义搜索

---

### Day 4 · 组装：知识助手 v1

**目标**：把 Day 2 + Day 3 拼起来，做出**能用**的 Agent

#### 项目结构
```
knowledge-agent/
  ingest.py       # 导入文档
  tools.py        # 工具集：search_notes, read_file
  agent.py        # 主循环
  memory/         # ChromaDB 数据
  notes/          # 你自己的笔记
```

#### 两个核心工具
- `search_notes(query)` → 从向量库检索
- `read_full_note(filename)` → 读整篇原文

LLM 自己决定：先搜索找线索，再读全文

**产出**：命令行里问"我上周记的关于 XX 的笔记讲了什么？"，Agent 能答出来

---

### Day 5 · 增强：记忆 + 多轮

**目标**：让 Agent 更像"助手"而不是"搜索框"

#### 任务清单
- [ ] 加**对话记忆**：保存最近 N 轮，超出用摘要压缩
- [ ] 加**打标签工具**：`add_tag(filename, tags)`
- [ ] 加**摘要工具**：`summarize_note(filename)`
- [ ] 处理常见坑：token 超限、工具报错、幻觉调用

**产出**：一个真正每天能用的私人笔记助手

---

### Day 6 · Streamlit Web UI

**目标**：让它"看起来像个产品"，同时把 Agent 引擎从 CLI 里拔出来

#### 任务清单
- [x] 把 `KnowledgeAgent` 抽成不做 IO 的类，`run_turn()` 返回结构化 `TurnResult`
- [x] 用 **Streamlit** 做网页 UI：侧栏（知识库状态 + tags/summary + 上传 + 重建索引 + 记忆压缩进度条）+ 主区（多轮对话 + 工具调用可折叠卡片）
- [x] CLI 模式（`python agent.py`）保留，行为与 Day 5 一致

**产出**：`streamlit run app.py` 就能启动的助手 · [教程](https://gip886.github.io/agents/day6.html)

---

### Day 7 · ReAct + 联网兜底 + 复盘

**目标**：给助手加两个能力扩展点（联网 + 显式思考），并对一周做结构化复盘

#### 任务清单
- [x] 加 `web_search` 工具（Tavily API，`TAVILY_API_KEY` 未配置时明确报错）
- [x] 加显式 **Thought**（ReAct 风格）：LLM 在 tool_call 消息的 content 里写"打算做什么"；兼容 Doubao 的 `reasoning_content` 字段
- [x] UI + CLI 都能看到每轮的 💭 Thought
- [x] 写 `REVIEW.md`：能力边界、踩过的坑、下一步方向

**产出**：能查笔记 + 联网兜底 + 全程可解释的 v4；[教程](https://gip886.github.io/agents/day7.html) · [复盘](./day7/REVIEW.md)

---

## 进阶项目方向

一周项目完成后，可以选下面进阶：

### 项目 B：自动化代码 Review Agent（难度 ⭐⭐⭐）
- 功能：读 Git diff，检查 bug/风格，生成 review 报告
- 涉及：Tool Use（读文件、跑测试）+ 多轮推理

### 项目 C：多 Agent 研究助手（难度 ⭐⭐⭐⭐）
- 功能：给定问题 → 规划者拆任务 → 搜索者查资料 → 写作者整合 → 校对者审查
- 涉及：多 Agent 协作 + 工具使用 + 规划

---

## 常见问题速查

| 报错 | 原因 & 解决 |
|------|------------|
| `AuthenticationError` | API Key 不对，检查 `.env` 是否有多余空格 |
| `model not found` | 应该填 `endpoint_id` 不是模型名 |
| `Connection error` | 网络问题，或 `base_url` 拼错了 |
| `ModuleNotFoundError: openai` | 忘了 `source venv/bin/activate` |
| Token 超限 | 用摘要压缩历史，或换更大 context 的模型 |

---

## 协作方式

1. **每天开工前**说"开始 Day X"，我给当天更详细的任务分解和代码骨架
2. **卡住随时问**：贴报错、贴代码，一起 Debug
3. **每天收工时**贴当天核心代码，我做简短 Review

---

## 参考资源

### 官方文档
- [火山方舟 API 文档](https://www.volcengine.com/docs/82379)
- [OpenAI Python SDK](https://github.com/openai/openai-python)
- [ChromaDB 文档](https://docs.trychroma.com/)
- [Streamlit 文档](https://docs.streamlit.io/)

### 必读文章
- [Lilian Weng - LLM Powered Autonomous Agents](https://lilianweng.github.io/posts/2023-06-23-agent/)
- [Anthropic - Building effective agents](https://www.anthropic.com/research/building-effective-agents)

### 框架
- [LangChain](https://python.langchain.com/)
- [LangGraph](https://langchain-ai.github.io/langgraph/)
- [Claude Agent SDK](https://docs.claude.com/en/api/agent-sdk/overview)

---

**开工愉快！** 🚀
