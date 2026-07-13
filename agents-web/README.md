# agents-web

Day 1-7 手写的 Python 知识助手的 **Next.js + TypeScript 版**。同样的能力（RAG + Tool Use + 记忆压缩 + ReAct + 联网兜底 + 流式对话），换成 Web 全栈 + 单一进程可部署到 Vercel。

## 跑起来

```bash
# 1. 环境变量（去 https://console.volcengine.com/ark 拿 endpoint id）
cp .env.example .env.local
# 编辑 .env.local，填入 ARK_API_KEY / ARK_ENDPOINT_ID / ARK_EMBEDDING_ENDPOINT_ID
# 可选：TAVILY_API_KEY

# 2. 装依赖
npm install

# 3. 启动
npm run dev
# 打开 http://localhost:3000
```

首次使用要**先建库**：侧栏点 "🔄 仅重建索引"，或者：

```bash
curl -X POST http://localhost:3000/api/ingest
```

`notes/` 目录预置了从 `day7/notes/` 拷过来的 3 篇 md，用作 demo。想加自己的笔记，直接拖到侧栏"上传笔记"里，或 `cp your.md notes/` 再点重建。

## 运行效果

问 "go 怎么处理错误的" 之后：

```
【主区】
  用户：go 怎么处理错误的
  助手：Go 处理错误的核心是**显式返回值**，函数通常将 `error` 类型作为最后一个返回值…
       ```go
       result, err := doSomething()
       if err != nil {
           return nil, fmt.Errorf("doSomething failed: %w", err)
       }
       ```
       - **错误包裹**：通过 `%w` 可嵌套错误…
       - **设计哲学**：错误被视为普通值…
       [来源: go-tips.md]

  ▸ 第 1 轮 · list_notes
      💭 思考：用户再次问"go怎么处理错误的"，看起来可能是之前的回答没有完全满足他们的需求，
              或者他们想确认更多细节。首先，我需要回顾之前的对话历史…
      🔧 list_notes {}

  ▸ 第 2 轮 · search_notes
      🔧 search_notes {"query":"Go 错误处理"}

  📊 3 轮 · 2 次工具调用 · 11094 tokens

【侧栏】
  📚 知识库：3 篇笔记 · 55 chunk
  🧠 对话记忆：3 条消息 · 3481 / 3000 字符  ← 进度条橙色告警
```

跑通的能力：
- ✅ 逐字流式（SSE token-by-token）
- ✅ ReAct Thought 可见（Doubao 的 `reasoning_content` 抓出来给用户看）
- ✅ 多轮工具调用可展开
- ✅ 引用溯源（`[来源: xxx.md]`）
- ✅ 代码块保留（```go … ```）
- ✅ Token 累加统计
- ✅ 记忆进度条 >80% 变橙提示

## 架构

```
┌────────────────────┐        ┌────────────────────────┐
│  app/page.tsx      │  SSE   │  app/api/chat/route.ts │
│  (Client React)    │◀───────│  (Streaming Response)  │
└────────────────────┘        └───────────┬────────────┘
                                          │
                                          ▼
                              ┌────────────────────────┐
                              │  lib/agent.ts          │
                              │  KnowledgeAgent        │
                              │  · runTurnStream()     │
                              │    async generator     │
                              └───┬──────────┬─────────┘
                                  │          │
                    ┌─────────────┘          └──────────┐
                    ▼                                    ▼
              ┌─────────┐                          ┌──────────┐
              │lib/tools│                          │lib/memory│
              │  7 tools│                          │  压缩逻辑│
              └────┬────┘                          └──────────┘
                   │
        ┌──────────┼──────────┐
        ▼          ▼          ▼
   ┌────────┐  ┌────────┐  ┌────────┐
   │ lib/kb │  │Tavily  │  │ lib/   │
   │ SQLite │  │(联网)  │  │embedding
   │+cosine │  │        │  │(火山方舟)
   └────────┘  └────────┘  └────────┘
```

**引擎/表现层分离**：`lib/agent.ts` 只 yield 事件、不做任何 HTTP/UI；API route 把事件转成 SSE；React 消费 SSE 更新组件状态。

## 关键文件（对照 Python 版）

| Web 版 | 对应 Python 版 | 说明 |
|---|---|---|
| `src/lib/agent.ts` | `day7/agent.py` | KnowledgeAgent，`runTurnStream` async generator |
| `src/lib/tools.ts` | `day7/tools.py` | 7 个工具 + Tavily web_search |
| `src/lib/memory.ts` | `day7/memory.py` | 对话记忆 + LLM 摘要压缩 |
| `src/lib/kb.ts` | `day7/knowledge_base.py` | **SQLite + 手写 cosine 替代 ChromaDB** |
| `src/lib/embedding.ts` | `day7/ark_embedding.py` | 火山方舟 multimodal embedding |
| `src/lib/chunk.ts` | `day7/knowledge_base.py::split_text` | 段落切分 + 长段滑窗 |
| `src/lib/frontmatter.ts` | `day7/frontmatter.py` | 极简 YAML frontmatter |
| `src/lib/sse-client.ts` | (Streamlit 内置) | 前端 SSE 消费器 |
| `src/app/page.tsx` | `day7/app.py` | 聊天 UI（React 版） |
| `src/app/api/chat/route.ts` | (无对应) | SSE 端点，把 runTurnStream 转成 event stream |

## 和 Python 版的差异

### 1. 向量库：ChromaDB → SQLite + 手写 cosine

Python 版用 ChromaDB（Docker/服务器），Web 版换成 **`better-sqlite3` 直接存 embedding blob**：

```ts
// src/lib/kb.ts
CREATE TABLE chunks (
  id TEXT PRIMARY KEY,
  file TEXT, chunk_idx INT, text TEXT,
  embedding BLOB,    -- Float32Array 字节序列
  tags TEXT
);

function cosineSimilarity(a, b) {
  let dot = 0, na = 0, nb = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    na += a[i] * a[i];
    nb += b[i] * b[i];
  }
  return dot / (Math.sqrt(na) * Math.sqrt(nb));
}
```

**为什么这样做**：
- 零外部服务：`data/kb.sqlite` 一个文件
- 可部署 Vercel serverless（chromadb JS 客户端还需要连一个远程 chroma 服务）
- 教学价值高：**手写一遍 cosine，就理解了"向量搜索"到底是什么**（3 行数学）
- 55 chunks 的检索延迟：< 5 ms

上万级 chunks 再换 `sqlite-vec` 或 `pgvector`。

### 2. 流式对话：Streamlit spinner → SSE 逐字流

Python Streamlit 只能等 tool loop 全部跑完再 render。Web 版用 **async generator + SSE**：

```ts
// lib/agent.ts
async *runTurnStream(userInput: string): AsyncGenerator<TurnEvent> {
  for (let round = 1; round <= this.maxRounds; round++) {
    const stream = await this.client.chat.completions.create({
      stream: true,
      stream_options: { include_usage: true },
      ...
    });
    for await (const chunk of stream) {
      if (delta.content) yield { type: "answer_delta", text: delta.content };
      if (delta.reasoning_content) yield { type: "thought_delta", text: ... };
      // tool_calls 按 index 归类分片累加...
    }
    // 执行工具、yield tool_call_start / tool_call_result
  }
  yield { type: "turn_done", result };
}
```

API route 把每个 yield 事件 `data: ${JSON}\n\n` 推出去；前端 `fetch().body.getReader()` 按行解析。

关键坑（详见 [docs/streaming-notes.md](../docs/streaming-notes.md)）：
- `tool_calls` 分片必须**按 `tc.index` 归类**（不能按到达顺序拼），否则并行 tool 的 arguments 会混
- `stream_options: { include_usage: true }` 别忘 —— 默认流式不返回 usage，token 会归零
- Doubao 系模型的 CoT 在 `reasoning_content` 字段而非 `content`

### 3. 前端框架：Streamlit → React

- **Streamlit**：每次交互从头重跑，`session_state` 存持久数据，逻辑和渲染混在一起
- **Next.js App Router**：正常 React 心智模型；`useState` 管本地状态、`fetch` 拉数据、SSE 更新 UI

## 已知限制 / 下一步

- **单进程**：`KnowledgeAgent` 挂在 `globalThis` 上，重启进程或 Vercel serverless 冷启动会丢对话记忆。要持久化就把 memory 写 SQLite
- **CLI 模式没做**：Python 版 `python agent.py` 有 REPL，Web 版没做对应 CLI。想要的话建个 `scripts/repl.ts` 用 Node.js readline
- **上传后前端 UI 有个已知点**：多个文件上传时 `Promise.all(file.text())` 大文件会一次性全读进内存，MVP 阶段 OK
- **Vercel 部署**：SSE 需要 `runtime: "nodejs"` 且 `maxDuration` 够（我们设了 60s）；SQLite 写入需要持久 filesystem —— Vercel 免费版是只读，得改成 Turso / Neon Postgres
- **Markdown 渲染**：当前答案用 `whitespace-pre-wrap` 展示，代码块被保留但没有语法高亮。真要给别人看，可以接 `react-markdown` + `rehype-highlight`

## 修过的两个非平凡 bug

写下来免得下次再踩：

### 1. globals.css 里的 `prefers-color-scheme: dark` 打架

`create-next-app` 默认给的 `globals.css` 里带一段：
```css
@media (prefers-color-scheme: dark) {
  :root { --background: #0a0a0a; --foreground: #ededed; }
}
```
在系统开了 dark mode 时 body 变黑，而我们组件用的都是硬编码亮色（`bg-white` / `bg-gray-50`），主区就变成黑底黑字看不清。

**修**：删掉 dark media query，body 加 `color-scheme: light` 锁定 UA 的默认样式（滚动条、input）为亮色。

### 2. 记忆压缩失败杀掉 turn，前端显示"(无回复)"

问到 3000+ 字符时会触发 `maybeCompress()` —— 里面调 LLM 生成摘要。这个 LLM 调用如果因为任何原因抛异常（网络、超时、模型抖动），整个 async generator 就死了，`turn_done` 事件永远发不出来。

前端拿不到 `turn_done`，用了 `finalTurn?.answer ?? "(无回复)"` 兜底，就把实际已经流出去的正文覆盖成了 "(无回复)"。

**两处都要修**：

```ts
// 后端 agent.ts：压缩独立 try/catch，答案已经流出去就不能因为压缩失败被吞掉
if (toolCallList.length === 0) {
  roundTrace.assistant_text = contentBuf || "(无回复)";
  rounds.push(roundTrace);
  let compression: CompressionEvent | null = null;
  try {
    compression = await this.memory.maybeCompress();
  } catch (e) {
    console.error("[maybeCompress] failed:", e);
  }
  yield { type: "turn_done", result: this.buildResult(...) };
  return;
}

// 前端 page.tsx：把"累加的答案"作为兜底真相源
let accumulatedAnswer = "";
// ...consumeSSE callback 里累加
// 组装 history 时：优先用 turn_done 里的 answer，退回到 accumulatedAnswer
const finalContent = (finalTurn?.answer && finalTurn.answer !== "(无回复)")
  ? finalTurn.answer
  : (accumulatedAnswer || "(无回复)");
```

另一个 React 反模式：**不要在 `setActive(prev => ...)` updater 里给外层闭包变量赋值**。updater 是纯函数、可能被 StrictMode 跑两次；setState 是异步的，闭包变量也不能同步反映事件。规矩：**setState updater 只做渲染同步；持久状态用普通闭包变量**。

## 未来可能的方向

- **切 Turso**（libSQL）：改一行 `import Database from ...`，直接上 Vercel
- **多 Agent 编排**：LangGraph.js 或者手写 handoff
- **可中断 streaming**：`AbortController` 传给 fetch，前端"停止"按钮触发
- **本地 LLM 后端**：`ARK_BASE_URL` 换成 `http://localhost:11434/v1`（Ollama）
