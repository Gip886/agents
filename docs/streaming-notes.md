# 流式对话（Streaming）设计笔记

> 起草日期：2026-07-13 · 状态：设计草稿，未实施
>
> 这份笔记是给"Day 8 加流式对话"这个后续动作准备的路线图。
> 当前 Day 1 的 `demo2_chat_loop.py` 已经跑通了**纯文本流**；Day 2 之后有
> `tool_calls`，流式的复杂度上一个台阶，需要一次专门的设计。

---

## 1. 先看已经有的：Day 1 的最小版本

`day1/demo2_chat_loop.py:66-91` 是最基础的例子：

```python
stream = client.chat.completions.create(
    model=MODEL,
    messages=messages,
    stream=True,
    stream_options={"include_usage": True},   # 默认 stream 不带 usage
)

full_reply = ""
for chunk in stream:
    if chunk.choices:
        delta = chunk.choices[0].delta.content
        if delta:
            print(delta, end="", flush=True)   # 一个字一个字打
            full_reply += delta
    if chunk.usage:                            # usage 只在最后一个 chunk 里
        turn_usage = chunk.usage
```

**核心心智模型**：`chunk = 一小段增量`。OpenAI 的字段叫 `delta`。**你要自己拼完整回复**（服务端不会给你一个"完整版"的兜底）。

---

## 2. 为什么 Day 7 上流式变复杂了

因为一个 assistant 消息里可能同时含 **content**、**tool_calls**、**reasoning_content**（Doubao 的 CoT 字段）。流式下这三样都是**分片段**过来的，交错到达。

Day 7 一次 tool_call 轮次的实际流大致长这样：

```
chunk 0: delta.role="assistant"
chunk 1: delta.reasoning_content="笔记"          ← Thought 也在流
chunk 2: delta.reasoning_content="里都是"
...
chunk N: delta.content="我"                     ← Thought 说完了开始正文
chunk N+1: delta.content="查一下最新的"
...
chunk M:  delta.tool_calls=[{index:0, function:{name:"web_search"}}]
chunk M+1: delta.tool_calls=[{index:0, function:{arguments:'{"que'}}]    ← 参数分片
chunk M+2: delta.tool_calls=[{index:0, function:{arguments:'ry":"Py'}}]
chunk M+3: delta.tool_calls=[{index:0, function:{arguments:'thon"}'}}]
chunk 末: usage=...
```

你要**边收边拼**，最后还原成 Day 6 那个非流式 `msg` 对象长的样子，再喂给 `execute_tool()`。

**关键坑**：`tool_calls` 分片必须按 **`tc.index`** 归类，不能按到达顺序拼。OpenAI 允许并行 tool_call —— index=0/1/2 三个 tool 的 name/arguments 是交错来的。

---

## 3. 三个复杂度层次（按性价比排）

| 层次 | 效果 | 改动量 | 值不值 |
|---|---|---|---|
| **L1：只流最终答案** | 前 N-1 轮工具调用照常等，最后一轮 LLM 输出文本时逐字显示 | ~30 行 | ⭐⭐⭐ 性价比最高 |
| **L2：+ Thought 也流** | 每轮工具调用前，用户能看到 💭 一个字一个字跳出来 | ~60 行 | ⭐⭐ 感官提升明显 |
| **L3：连 tool_call 参数也流** | 显示"Agent 正在写 arguments…"，看着它一个字符一个字符拼 JSON | ~100 行 | ⭐ 炫技用，实用价值有限 |

**推荐路径**：一步到位做 L1 + L2；L3 跳过。

---

## 4. 设计：`run_turn_stream()` 平行接口

保留老的 `run_turn()` 不动（CLI 冒烟测试、单元测试都在用），新加一个 generator 版本。

### 4.1 事件类型（新加到 `agent.py`）

```python
from dataclasses import dataclass

@dataclass
class ThoughtDelta:    text: str        # Thought 又蹦出一段
@dataclass
class AnswerDelta:     text: str        # 最终答案又蹦出一段
@dataclass
class ToolCallStart:   name: str; arguments: str
@dataclass
class ToolCallResult:  name: str; result: str
@dataclass
class TurnDone:        result: TurnResult   # 结束，带完整 TurnResult

TurnEvent = ThoughtDelta | AnswerDelta | ToolCallStart | ToolCallResult | TurnDone
```

### 4.2 主循环骨架

```python
def run_turn_stream(self, user_input: str):
    """Streaming 版。yield 一系列事件，最后 yield TurnDone(TurnResult)"""
    self.memory.append({"role": "user", "content": user_input})
    rounds = []

    for round_num in range(1, self.max_rounds + 1):
        round_trace = RoundTrace(round_num=round_num)

        stream = self.client.chat.completions.create(
            model=self.model,
            messages=self.memory.get_messages(),
            tools=TOOLS_SCHEMA,
            stream=True,
            stream_options={"include_usage": True},
        )

        # 累加器：这轮 assistant 消息的完整体
        content_buf = ""
        reasoning_buf = ""
        tool_calls_buf = {}   # index -> {id, name, arguments}
        usage = None

        for chunk in stream:
            if not chunk.choices:
                if chunk.usage:
                    usage = chunk.usage
                continue
            delta = chunk.choices[0].delta

            # (1) content 分片 —— 边收边 yield
            if delta.content:
                content_buf += delta.content
                yield AnswerDelta(delta.content)

            # (2) reasoning_content 分片（Doubao）
            if getattr(delta, "reasoning_content", None):
                reasoning_buf += delta.reasoning_content
                yield ThoughtDelta(delta.reasoning_content)

            # (3) tool_calls 分片 —— 用 index 归类
            for tc in (delta.tool_calls or []):
                slot = tool_calls_buf.setdefault(tc.index,
                    {"id": None, "name": "", "arguments": ""})
                if tc.id:
                    slot["id"] = tc.id
                if tc.function:
                    if tc.function.name:
                        slot["name"] += tc.function.name
                    if tc.function.arguments:
                        slot["arguments"] += tc.function.arguments

        # 流结束，把累加的 message 拼回 non-stream 那样的 dict
        msg_dict = {"role": "assistant", "content": content_buf or None}
        if tool_calls_buf:
            msg_dict["tool_calls"] = [
                {"id": s["id"], "type": "function",
                 "function": {"name": s["name"], "arguments": s["arguments"]}}
                for s in tool_calls_buf.values()
            ]
        self.memory.append(msg_dict)

        if usage:
            round_trace.prompt_tokens = usage.prompt_tokens
            round_trace.completion_tokens = usage.completion_tokens

        # 没 tool_calls：这就是最终答案
        if not tool_calls_buf:
            round_trace.assistant_text = content_buf or "(无回复)"
            rounds.append(round_trace)
            compression = self.memory.maybe_compress()
            yield TurnDone(TurnResult(
                answer=content_buf, rounds=rounds,
                compression_event=compression,
            ))
            return

        # 有 tool_calls：先记 Thought 到 trace
        # 优先 content（Claude/GPT），次选 reasoning_content 首段（Doubao）
        thought = content_buf.strip()
        if not thought and reasoning_buf:
            thought = reasoning_buf.split("\n", 1)[0].strip()[:240]
        round_trace.thought = thought

        # 执行工具（这一步不流式）
        for slot in tool_calls_buf.values():
            yield ToolCallStart(name=slot["name"], arguments=slot["arguments"])
            result = execute_tool(slot["name"], slot["arguments"], ctx=self.tool_ctx)
            round_trace.tool_calls.append(ToolCallTrace(
                name=slot["name"], arguments=slot["arguments"], result=result,
            ))
            self.memory.append({
                "role": "tool", "tool_call_id": slot["id"], "content": result,
            })
            yield ToolCallResult(name=slot["name"], result=result)

        rounds.append(round_trace)
```

---

## 5. Streamlit 侧消费（app.py）

Streamlit 1.28+ 有 `st.write_stream`，但它只吃"纯字符串流"。我们的事件流有 content / tool call / done 三类，得手动做 —— `st.empty()` 占位符 + 每次覆盖写整段：

```python
if user_input:
    st.session_state.history.append({"role": "user", "content": user_input, "turn": None})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        answer_placeholder = st.empty()
        status_placeholder = st.empty()
        answer_buf = ""
        turn_result = None

        for event in st.session_state.agent.run_turn_stream(user_input):
            if isinstance(event, AnswerDelta):
                answer_buf += event.text
                answer_placeholder.markdown(answer_buf + "▌")     # 光标闪烁
            elif isinstance(event, ToolCallStart):
                status_placeholder.caption(f"🔧 正在调用 `{event.name}`…")
            elif isinstance(event, ToolCallResult):
                status_placeholder.caption(f"✅ `{event.name}` 完成")
            elif isinstance(event, TurnDone):
                turn_result = event.result

        answer_placeholder.markdown(answer_buf)   # 收工去掉光标
        status_placeholder.empty()                 # 清掉状态提示
        render_turn_trace(turn_result)             # 展开工具轨迹（Day 6 那套不变）

    st.session_state.history.append({
        "role": "assistant", "content": turn_result.answer, "turn": turn_result,
    })
    st.rerun()
```

**⚠️ 关键 Streamlit 坑**：
- 老历史消息**不能**走 streaming（rerun 时会把每个字符重播一遍）。加个 `if msg is new_this_turn` 的判据，只对**最新**这一条走 streaming 路径。
- 别用 `with st.spinner("思考中")` —— 字都在跳了，spinner 反而多余。改成 `caption("🔧 正在调用…")` 更好。

---

## 6. CLI 侧消费（agent.py main）

改动很小：

```python
for event in agent.run_turn_stream(user_input):
    if isinstance(event, AnswerDelta):
        print(event.text, end="", flush=True)
    elif isinstance(event, ThoughtDelta):
        pass   # CLI 不打 Thought delta 太吵，等 TurnDone 后一起打一句
    elif isinstance(event, ToolCallStart):
        print(f"\n  🔧 {event.name}({event.arguments[:60]}…)", flush=True)
    elif isinstance(event, ToolCallResult):
        preview = event.result[:100].replace("\n", " ")
        print(f"     ↳ {preview}", flush=True)
    elif isinstance(event, TurnDone):
        result = event.result
        print()   # 换行
```

---

## 7. 会踩的坑

| 坑 | 原因 / 解决 |
|---|---|
| token 统计变 0 | 忘了 `stream_options={"include_usage": True}` |
| tool_calls 参数拼出来是坏 JSON | 没按 `tc.index` 归类，两个并行 tool 的 arguments 拼混了 |
| Doubao 的 `reasoning_content` 特别长，一 chunk 一 chunk 刷屏 | ThoughtDelta 只显示前 N 字，或者干脆等整段收完再一次性亮 |
| 中途用户点 Stop，Agent 已 append 了半截 assistant 消息 | try/finally + `_pending_msg` 缓冲；abort 时不 append，回滚记忆 |
| Streamlit 里 `st.empty()` 每次 rerun 都重建 | 老历史消息用 `st.markdown()` 一次性显示，**只对新消息**跑 streaming |
| for chunk 阻塞 Streamlit 主线程 | 不需要 spinner —— 字符流本身就是"活着"的证据 |
| 用户重复点提交 | 加一个 `st.session_state.streaming = True` flag，进行中把 `st.chat_input` 禁用 |
| Doubao 的 `delta.tool_calls` 有时是 `None` | 用 `(delta.tool_calls or [])` 兜底 |

---

## 8. 实施 checklist（真到 Day 8 时按这个走）

- [ ] `cp -r day7 day8`
- [ ] `agent.py`：加事件 dataclass、加 `run_turn_stream()` generator，保留老 `run_turn()`
- [ ] `agent.py` CLI main：改用 `run_turn_stream()`，事件分派 print
- [ ] `app.py`：主循环改成事件循环 + `st.empty()` 占位符 + streaming flag 禁用输入
- [ ] `app.py`：老历史消息渲染路径不动（不 streaming），只有本次输入走 stream
- [ ] 冒烟测试：
  - [ ] 纯本地问题 —— 看到 tool_call 提示 + 最终答案逐字显示
  - [ ] 联网兜底 —— 两轮 tool_call 状态提示都出现
  - [ ] 长回答 —— 光标 `▌` 一直闪，答案越来越长
  - [ ] token 统计不为 0
- [ ] 写 `docs/day8.html`、更新导航
- [ ] `REVIEW.md` 加一段"streaming 上线后感受"

---

## 9. 更进一步的方向

做完 streaming 之后，还可以：

- **可中断的 streaming**：暴露 `abort_event: threading.Event`，用户点"停止"时 `stream.close()`，回滚未完成消息
- **打字机效果调速**：字符间加 `time.sleep(0.01)` 让节奏更"人性" —— 但会牺牲吞吐；实用 UI 里通常不做
- **多轮工具调用的进度条**：现在 UI 里 `第 N 轮`是一个 st.status；streaming 时可以在头顶显示"Round 2 / 8"
- **服务器发送事件（SSE）** —— 如果以后要把 agent 拆成后端 API，SSE 是标准做法。`fastapi` + `httpx` 就能起

---

## 10. 参考

- OpenAI streaming: https://platform.openai.com/docs/api-reference/streaming
- Anthropic streaming: https://docs.claude.com/en/api/messages-streaming
- 火山方舟（Doubao）流式响应: https://www.volcengine.com/docs/82379
- Streamlit `st.write_stream`: https://docs.streamlit.io/develop/api-reference/write-magic/st.write_stream
