"""
对话记忆管理
====================================
Day 4 的问题：messages 越聊越长 → token 爆炸 + 慢 + 贵。

Day 5 的做法：
  - 系统 prompt 永远保留（第一条）
  - 最近 KEEP_RECENT_ROUNDS 轮完整对话保留
  - 中间的旧对话，超过 TRIGGER_CHARS 阈值时，交给 LLM 摘要成 1 条 system 消息

关键坑：
  一个"轮次"可能是多条 message：
    user → assistant(tool_calls) → tool → assistant(tool_calls) → tool → assistant(final)
  压缩时必须在"轮次边界"切分，不能切在 tool_call 中间，否则 API 会报错
  ("tool_calls" 必须紧跟 "tool" 响应)。
"""
from __future__ import annotations

from typing import Any


# 触发压缩的字符数阈值（粗略估计：中文 ~1.5 字符/token；3000 字符约 2000 tokens）
TRIGGER_CHARS = 3000

# 保留最近多少个完整轮次（不压缩）
KEEP_RECENT_ROUNDS = 3


def _msg_chars(msg: dict) -> int:
    """粗算一条消息的字符数（够用就行）"""
    n = 0
    content = msg.get("content")
    if isinstance(content, str):
        n += len(content)
    # tool_calls 里 arguments 也算
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        n += len(fn.get("arguments") or "")
        n += len(fn.get("name") or "")
    return n


def _find_round_boundaries(messages: list[dict], start_idx: int) -> list[int]:
    """
    从 start_idx 开始扫描，返回每个"轮次起点"的下标。
    轮次起点 = role == "user" 的位置。
    保证在轮次起点切分不会破坏 tool_call ↔ tool response 的配对。
    """
    return [i for i, m in enumerate(messages) if i >= start_idx and m.get("role") == "user"]


class ConversationMemory:
    """
    维护一条对话的所有 message，超阈值时自动压缩。

    用法：
        mem = ConversationMemory(system_prompt="...", summarize_fn=my_summarize)
        mem.append({"role": "user", "content": "..."})
        for msg in mem.get_messages():
            ...
        event = mem.maybe_compress()   # 返回压缩事件（如果发生了），供 agent 打印
    """

    def __init__(
        self,
        system_prompt: str,
        summarize_fn,
        trigger_chars: int = TRIGGER_CHARS,
        keep_recent_rounds: int = KEEP_RECENT_ROUNDS,
    ):
        self.system_prompt = system_prompt
        self.summarize_fn = summarize_fn   # 传入 (messages_to_summarize) -> str
        self.trigger_chars = trigger_chars
        self.keep_recent_rounds = keep_recent_rounds

        # messages[0] 恒为 system prompt。压缩后 messages[1] 可能变成 "对话摘要" 的 system 消息。
        self.messages: list[dict] = [{"role": "system", "content": system_prompt}]

    # ---------- 基本读写 ----------

    def append(self, msg: dict | Any):
        """追加一条消息。dict 或者带 model_dump 的 pydantic 对象都可以。"""
        if hasattr(msg, "model_dump"):
            msg = msg.model_dump(exclude_none=True)
        self.messages.append(msg)

    def extend(self, msgs: list[dict]):
        for m in msgs:
            self.append(m)

    def get_messages(self) -> list[dict]:
        """返回给 LLM 的 messages（就地引用，别改）"""
        return self.messages

    def total_chars(self) -> int:
        return sum(_msg_chars(m) for m in self.messages)

    def clear(self):
        """清空历史（保留 system prompt）"""
        self.messages = [{"role": "system", "content": self.system_prompt}]

    # ---------- 压缩 ----------

    def maybe_compress(self) -> dict | None:
        """
        如果超过阈值就压缩。返回压缩事件 dict 供 agent 打印；没压缩返回 None。

        压缩事件字段：
          - before_chars, after_chars
          - before_msgs, after_msgs
          - summary_preview
        """
        if self.total_chars() < self.trigger_chars:
            return None

        # 找出所有 user 消息的下标（每个 user 是一轮的起点）
        # 从下标 1 开始（跳过 system prompt；如果 messages[1] 也是 system 摘要则也跳过）
        first_scan = 1
        while first_scan < len(self.messages) and self.messages[first_scan].get("role") == "system":
            first_scan += 1

        round_starts = _find_round_boundaries(self.messages, first_scan)

        # 至少要留 keep_recent_rounds 轮，才谈得上压缩
        if len(round_starts) <= self.keep_recent_rounds:
            return None

        # 分界点：保留 round_starts[-keep_recent_rounds] 开始的所有消息
        keep_from = round_starts[-self.keep_recent_rounds]

        # system prompt 后 ~ keep_from 之间的旧消息需要压缩
        old_prefix = [m for m in self.messages[:keep_from] if m.get("role") == "system"]
        old_convo = self.messages[len(old_prefix):keep_from]
        recent = self.messages[keep_from:]

        if not old_convo:
            return None

        before_chars = self.total_chars()
        before_msgs = len(self.messages)

        # 调 LLM 摘要
        summary_text = self.summarize_fn(old_convo)

        summary_msg = {
            "role": "system",
            "content": f"[对话历史摘要 — {len(old_convo)} 条旧消息已压缩]\n{summary_text}",
        }

        # 重组：system prompt + (已有 system 摘要，如果有的话) + 新摘要 + 最近轮次
        # 简化：只保留原始 system prompt，把所有旧摘要合并成一条新摘要
        new_messages = [self.messages[0], summary_msg] + recent
        self.messages = new_messages

        after_chars = self.total_chars()
        after_msgs = len(self.messages)

        return {
            "before_chars": before_chars,
            "after_chars": after_chars,
            "before_msgs": before_msgs,
            "after_msgs": after_msgs,
            "summary_preview": summary_text[:120] + ("..." if len(summary_text) > 120 else ""),
        }


# ================================================================
# 一个默认的摘要函数（用同一套 OpenAI client 生成摘要）
# ================================================================

def make_llm_summarizer(client, model: str):
    """
    返回一个 summarize_fn(messages) -> str，用给定的 chat client 生成摘要。
    """
    def summarize(messages_to_compress: list[dict]) -> str:
        # 把待压缩的消息转成"叙述文本"
        lines = []
        for m in messages_to_compress:
            role = m.get("role")
            content = m.get("content") or ""
            if role == "user":
                lines.append(f"用户: {content}")
            elif role == "assistant":
                tool_calls = m.get("tool_calls")
                if tool_calls:
                    calls = [
                        f"{tc['function']['name']}({tc['function']['arguments']})"
                        for tc in tool_calls
                    ]
                    lines.append(f"助手[调用工具]: {'; '.join(calls)}")
                if content:
                    lines.append(f"助手: {content}")
            elif role == "tool":
                # 工具结果只取前 200 字（摘要不需要完整原文）
                trimmed = content[:200] + ("..." if len(content) > 200 else "")
                lines.append(f"工具返回: {trimmed}")
            elif role == "system":
                # 之前的摘要
                lines.append(f"[之前摘要] {content}")

        conversation_text = "\n".join(lines)

        prompt = (
            "下面是一段人机对话的历史片段。请用简洁的中文（不超过 200 字）总结：\n"
            "1) 用户问过哪些问题\n"
            "2) 助手做过哪些关键操作、给出了什么核心结论\n"
            "3) 涉及到了哪些笔记文件（如果有）\n"
            "只输出摘要正文，不要客套。\n\n"
            "----对话----\n"
            f"{conversation_text}"
        )

        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一个对话摘要助手，输出精炼、无冗余。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        return resp.choices[0].message.content or "(摘要生成失败)"

    return summarize
