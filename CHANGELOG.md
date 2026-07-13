# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/) 的写法，版本号遵循 [SemVer](https://semver.org/)。

---

## [1.0.0] — 2026-07-13

### 🎉 首个里程碑版本

一份为 Java/Go 后端开发者定制的 Agent 入门项目，7 天从零手写 + 一份 Next.js 全栈实现。

### Added

#### Python 教学版（`day1/` … `day7/`）

- **Day 1** — LLM 首次调用：单轮 / 多轮对话、streaming、token 统计
- **Day 2** — Tool Use：手写完整 agent loop、工具 schema、错误恢复
- **Day 3** — RAG：段落切分 + 滑窗、火山方舟 embedding、ChromaDB 语义检索
- **Day 4** — 组装知识助手 v1：工具 + RAG 融合
- **Day 5** — 记忆增强：ConversationMemory 自动摘要压缩、写入工具（add_tag / summarize_note）、YAML frontmatter 手写解析器
- **Day 6** — Streamlit Web UI：引擎/表现层分离、`TurnResult` 结构化协议、上传 + 重建索引、记忆压缩可视化
- **Day 7** — ReAct + 联网兜底：Thought 显式化（兼容 Doubao 的 `reasoning_content`）、Tavily `web_search`、一周复盘

#### Web 全栈版（`agents-web/`）

- **Next.js 16** + React 19 + TypeScript + Tailwind v4（App Router）
- **SQLite + 手写 cosine similarity** 替代 ChromaDB —— 零外部服务、可 Vercel、教学价值高（三行数学看懂向量搜索）
- **流式对话**：async generator + SSE，token-by-token 逐字显示
- 完整 7 个工具、对话记忆压缩、ReAct Thought、Tavily 联网兜底
- API routes：`/api/chat`（SSE）、`/api/chat/reset`、`/api/ingest`、`/api/notes`、`/api/memory`

#### 文档

- **教程网站**：10 个页面部署在 [gip886.github.io/agents](https://gip886.github.io/agents/)
- **`docs/streaming-notes.md`**：流式对话设计笔记（Python 版路线图）
- **`agents-web/README.md`**：跑起来 + 架构 + 与 Python 版对比 + 修过的两个非平凡 bug
- **`day7/REVIEW.md`**：一周复盘（技术脉络、能力边界、下一步方向）

#### Release 附件

- **`agents-web-standalone-v1.0.0.tar.gz`** —— Next.js `output: "standalone"` 构建产物（~11 MB 压缩，~37 MB 解压后），用户 `tar xzf` → 编辑 `.env.local` → `node server.js` 三步启动，不需要 `npm install`

### Known Limitations

- `agents-web` 的 `KnowledgeAgent` 挂在 `globalThis`，Vercel serverless 冷启动会丢对话记忆（想跨请求持久化就写 SQLite）
- Standalone 包只对当前平台 CPU 架构编译 `better-sqlite3`；跨架构部署时需重装
- 答案的 Markdown 渲染当前用 `whitespace-pre-wrap`，代码块保留但没语法高亮
- Python 版最大轮次 8 轮，需要长任务规划的场景会截断

### Roadmap（下一步方向）

按优先级排：

- 🟢 写操作二次确认（`add_tag` / `summarize_note` UI 弹确认框）
- 🟢 换 Turso（libSQL）跑 Vercel
- 🟢 可中断 streaming（`AbortController` + 前端"停止"按钮）
- 🟡 Markdown 渲染 + 代码高亮（`react-markdown` + `rehype-highlight`）
- 🟡 PDF 支持（`pypdf` + 现有 chunking）
- 🟡 用 LangGraph.js 重写主循环
- 🔴 多 Agent 编排（Planner + Searcher + Writer）
- 🔴 代码 Review Agent（读 git diff、跑测试、写 review comment）

### Full Commit History

```
3131c5a agents-web: UI 样式修复 + 两个非平凡 bug 修复
1d60fd8 agents-web: Next.js + TypeScript 全栈版
6fcdb43 Day 7 完成：ReAct + 联网兜底 + 一周复盘
09510fc docs: 新增 Day 6 教程页 + 全站导航同步
bca2237 Day 6 完成：Streamlit Web UI
313020a Day 5 完成：记忆增强 + 打标签/摘要工具
55db548 Day 4 完成：组装知识助手 v1（RAG + Tool Use 融合）
313baa4 Day 3 完成：RAG 向量检索
137842f Day 2 完成：Tool Use 工具调用（观察 + 完整 Agent Loop）
9b05b44 Day 1 完成：单轮 + 多轮 Streaming + Token 统计
a770aa8 搭建学习站点 + Day 1 教程结构
11f8a7a 初始化：Agent 学习计划与项目结构
```

[1.0.0]: https://github.com/Gip886/agents/releases/tag/v1.0.0
