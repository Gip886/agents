# 一周复盘：从 zero 到"能用的" Agent

> 收工时间：2026-07-12（Day 7）· 起始时间：一周前

## 一句话总结

用 7 天从"没写过 LLM 代码"到有一个 **RAG + Tool Use + 记忆压缩 + ReAct + 联网兜底** 的私人知识助手；
命令行和 Web 两个前端，共用一个 `KnowledgeAgent` 引擎；代码总量 ~1400 行，无框架依赖（除了 `openai` / `chromadb` / `streamlit` 这几个"数据管道"）。

---

## 七天的技术脉络

| Day | 主题 | 核心产出 | 一句话学到 |
|-----|------|---------|-----------|
| 1 | LLM 首次调用 | 单轮 / 多轮 / streaming | messages 就是一个 role+content 数组，历史全靠客户端拼 |
| 2 | Tool Use | 手写完整 agent loop | 工具调用是"LLM 返回 JSON → 你解析 → 你执行 → 再喂回去"的循环 |
| 3 | RAG | chunking + embedding + ChromaDB | 相似度 < 0.4 就是"没找到"，比阈值瞎调关键词有用 |
| 4 | 组装 v1 | RAG 当作一个工具塞进 loop | Agent = 工具能力 × 组合方式；工具的 description 是隐性 prompt |
| 5 | 记忆增强 | 对话压缩 + 写入工具 + frontmatter | 切分轮次不能切在 tool_call 中间；元数据要跟数据走 |
| 6 | Streamlit Web UI | 引擎/表现层分离 · `TurnResult` | 类里出现 `print` 就是没拆干净；UI 应该消费结构化数据 |
| 7 | ReAct + 联网 | Thought 字段 + `web_search` 兜底 | Thought 靠 prompt 教 + `reasoning_content` fallback；兜底工具的 description 就是"什么时候别用我" |

---

## 能力边界（这个助手能做什么、不能做什么）

### ✅ 现在能做的

- **私人笔记问答**：语义检索 + 全文补齐 + 引用来源
- **多轮上下文**：能记住"你刚说的那个 xxx"—— 只要没超过压缩阈值
- **长对话不炸**：字符数 ≥ 3000 触发摘要压缩，保留最近 3 轮完整对话
- **反向整理笔记**：加标签、生成摘要，写回 frontmatter（`git diff` 友好）
- **本地找不到时联网兜底**：Tavily API（需 key）
- **两种前端**：CLI（`python agent.py`）+ Web（`streamlit run app.py`），业务逻辑零重复
- **可解释性**：每轮工具调用轨迹 + Thought 都能在 UI 里展开看

### ❌ 现在不能做的（下一步方向）

- **不会写代码 / 执行代码**：需要 code_interpreter 类工具（Docker 沙盒里跑 Python）
- **不会跨文档"推理链"**：比如"我在 A 笔记提到的那个方案在 B 笔记里怎么演化的"—— 现在只能靠单次检索的 top_k
- **不会规划长任务**：`max_rounds = 8`，任何需要 10+ 步的任务会被截断
- **压缩后信息有损**：摘要是 LLM 生成的，早期细节问不出来了
- **单用户单进程**：Chroma、frontmatter 都是本地文件；多用户要换 Postgres + pgvector
- **无审计 / 无回滚**：`add_tag` / `summarize_note` 直接改文件，改错了只能 git checkout
- **成本模糊**：token 累计能看到，但没有"这次任务花了多少钱"

### ⚠️ 已知隐患

- **Prompt 是唯一护栏**：LLM 会不会乱调 `add_tag` / `summarize_note`，全靠 system prompt 的第 6 条。真部署要加"写操作需要用户确认"的 UI 二次确认
- **相似度阈值 0.4 是拍脑袋定的**：换个 embedding 模型可能就不对了；理想是自动校准
- **frontmatter 解析器很朴素**：不支持嵌套 / 多行字符串。目前笔记全是 tags + summary 够用
- **`memory.py` 的压缩没有"重要性权重"**：老话题被压掉可能失去关键上下文

---

## 每天最"卡"的一件事 & 学到什么

- **Day 1**：把 base_url 拼错了。教训：先 `curl` API endpoint，别直接跳 SDK
- **Day 2**：LLM 在没工具的问题上也硬调工具（"你好"→ 也去 search）。教训：system prompt 里明确"闲聊不用工具"
- **Day 3**：chunk 切太大（500 字），检索全命中同一段。教训：先看 chunk 分布再定 top_k
- **Day 4**：一个 turn 内 LLM 循环调 search 三次都用同一个 query。教训：加"重复 query 最多 2 次"的规则
- **Day 5**：压缩切在 tool_call 中间 → 400 错误。教训：**在 user 消息处切**，boundary 要跟着消息角色走
- **Day 6**：`st.session_state.agent = KnowledgeAgent()` 没加存在性判断 → 每次 rerun 记忆清零。教训：Streamlit 的执行模型是"从头跑一遍"
- **Day 7**：LLM 在 tool_call 消息里 content 是空的。教训：Doubao 系模型把 CoT 放在 `reasoning_content` 字段；两条腿走（prompt + fallback）才稳

---

## 架构复盘：现在长什么样

```
┌─────────────┐     ┌─────────────┐
│  agent.py   │     │   app.py    │   ← 表现层
│   (CLI)     │     │ (Streamlit) │
└──────┬──────┘     └──────┬──────┘
       │                   │
       └────────┬──────────┘
                ▼
     ┌──────────────────────┐
     │   KnowledgeAgent     │      ← 引擎（不做 IO）
     │   .run_turn() ─→     │
     │   TurnResult         │
     └──┬────────┬─────────┬┘
        │        │         │
        ▼        ▼         ▼
   ┌────────┐┌──────┐┌───────────┐
   │ tools  ││memory││knowledge_ │  ← 三个横向模块
   │        ││      ││   base    │
   │ 7 工具 ││ 压缩 ││ 建库/搜索 │
   └───┬────┘└──────┘└─────┬─────┘
       │                   │
       ▼                   ▼
   ┌────────┐          ┌─────────┐
   │Tavily  │          │ Chroma  │
   │(联网)  │          │  (向量) │
   └────────┘          └─────────┘
```

**关键结构决策**：
- **每一层单向依赖**：UI → Agent → tools → 外部服务。反向依赖零。
- **`TurnResult` 是唯一的层间协议**：CLI 和 UI 都拿它，改 UI 不改引擎
- **`ToolContext` 传 LLM client 给工具**：避免全局变量，也不用每个工具都硬塞 client 参数
- **frontmatter 是"人可读的元数据"**：不引入 SQLite / JSON 旁路，用户 `cat` 就能看到

---

## 每天代码量粗算

| Day | 新增行数（含注释） | 累计目录大小 |
|-----|-------------------|-------------|
| 1 | ~200 | 200 |
| 2 | ~250 | 450 |
| 3 | ~280 | 730 |
| 4 | ~350 | 1080 |
| 5 | ~420 | 1500 |
| 6 | ~220 | 1720 |
| 7 | ~180 | 1900 |

> 数字不含 venv / chroma_db。每天是"拷贝上一天 + 增量改"，实际"净新增"更少 —— 一半时间在改 system prompt。

---

## 下一步方向（按优先级排）

### 🟢 立刻能做（1-2 天）

1. **写操作二次确认**：`add_tag` / `summarize_note` 弹一个"确认修改 xxx.md？"对话框
2. **流式回答**：`response.stream = True`，Streamlit 里用 `st.write_stream` 逐字显示
3. **导出对话**：一键把 `st.session_state.history` 导成 markdown 放到 notes/ 里
4. **成本面板**：Doubao 有 in/out token 单价，侧栏加一个"本次会话花了 ¥X"

### 🟡 值得深入（3-5 天）

5. **多模型比较**：同一个问题让 Doubao / Claude / GPT 各答一次，UI 里对比 —— 学 [claude-api](https://docs.claude.com/api) 或 OpenAI SDK
6. **PDF 支持**：`pypdf` + 现有 chunking 流程；难点是标题层级识别
7. **用 LangGraph 重写主循环**：看看框架是否让 tool loop / 状态机更清晰。做完写篇"手写 vs LangGraph"对比
8. **ReAct 显式化**：现在 Thought 只做展示，可以改成"LLM 输出 Thought → 判断是否要 Act → …"的显式状态机

### 🔴 更大的项目（1-2 周）

9. **多 Agent 研究助手**：Planner + Searcher + Writer + Reviewer 四个 Agent 协作。学 handoff / shared memory
10. **代码 Review Agent**：读 git diff，跑测试，写 review comment。工具链更重（读文件 / 跑 shell / 分析 AST）
11. **自动学习触发**：Agent 观察到"用户又问了 rag-notes.md 里的 X 3 次" → 自动 summarize + 加高频访问标签

---

## 对"Agent 是什么"的一句话理解（写在最后）

**Agent = LLM + 结构化的工具调用循环 + 你精心维护的上下文。**

LLM 只是那个"每一步决定下一步做什么"的核心；真正让它变强的是：
- 你给了它多少工具、每个工具的 description 写得多准
- 你的上下文（memory + RAG 检索出来的片段）质量多高
- 你的循环终止条件、错误恢复策略有多鲁棒

框架（LangChain / LangGraph）把 loop / memory / tool 都做好了，但入门时**先手写一遍**很值 —— 你会知道每个"神奇"的功能背后其实就是 20-50 行代码 + 一个 prompt。

一周结束，感觉不像"学了 Agent"，倒像"重新认识了一遍软件工程" —— 只是把 "if / for" 换成 "LLM decide"，其它工程直觉全部适用。

—— Day 7 · 收工 🚀
