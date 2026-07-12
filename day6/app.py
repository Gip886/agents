"""
知识助手 Web UI（Day 6）
====================================
基于 Streamlit 的网页界面。业务逻辑完全复用 agent.py 里的 KnowledgeAgent。

跑法：
    streamlit run app.py
"""
from __future__ import annotations

import io
import time
from pathlib import Path

import streamlit as st

from agent import KnowledgeAgent, TurnResult
from knowledge_base import KnowledgeBase, NOTES_DIR
from tools import init_kb


st.set_page_config(
    page_title="知识助手 v3",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ================================================================
# Session state 初始化
# ================================================================

def _init_state():
    """所有状态一次性初始化"""
    if "agent" not in st.session_state:
        st.session_state.agent = KnowledgeAgent()
    if "history" not in st.session_state:
        # history[i] 是 dict: {"role": "user"/"assistant", "content": str, "turn": TurnResult|None}
        st.session_state.history = []
    if "session_tokens" not in st.session_state:
        st.session_state.session_tokens = 0
    if "ingest_notice" not in st.session_state:
        # 一次性提示（上传成功/建库完成后显示一次，然后清空）
        st.session_state.ingest_notice = None


_init_state()


# ================================================================
# 侧栏：知识库状态 + 上传 + 记忆
# ================================================================

with st.sidebar:
    st.title("📚 知识库")

    kb: KnowledgeBase = init_kb()
    try:
        chunk_count = kb.collection.count()
    except Exception:
        chunk_count = 0
    notes = kb.list_notes()

    if chunk_count == 0:
        st.warning("知识库为空，请上传笔记后点击「重建索引」")
    else:
        st.success(f"{len(notes)} 篇笔记 · {chunk_count} 个 chunk")

    with st.expander(f"📄 笔记列表（{len(notes)}）", expanded=False):
        if not notes:
            st.caption("（还没有笔记）")
        for name in notes:
            try:
                meta = kb.read_meta(name)
            except Exception:
                meta = {}
            tags = meta.get("tags") or []
            summary = meta.get("summary")
            st.markdown(f"**{name}**")
            if tags:
                st.caption("🏷️ " + " · ".join(f"`{t}`" for t in tags))
            if summary:
                st.caption(f"📝 {summary}")

    st.divider()

    # ---------- 上传 ----------
    st.subheader("📤 上传笔记")
    uploaded_files = st.file_uploader(
        "拖入 .md 文件",
        type=["md", "markdown"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    col_up1, col_up2 = st.columns(2)
    with col_up1:
        if st.button("💾 保存到 notes/", disabled=not uploaded_files, use_container_width=True):
            notes_path = Path(NOTES_DIR)
            notes_path.mkdir(exist_ok=True)
            saved = []
            for uf in uploaded_files:
                dest = notes_path / uf.name
                dest.write_bytes(uf.getbuffer())
                saved.append(uf.name)
            st.session_state.ingest_notice = f"✅ 已保存 {len(saved)} 个文件：{', '.join(saved)}\n点击「重建索引」使其可检索"
            st.rerun()

    with col_up2:
        if st.button("🔄 重建索引", type="primary", use_container_width=True):
            with st.spinner("正在建库（切分 + embedding）…"):
                try:
                    n_files, n_chunks = kb.rebuild()
                    st.session_state.ingest_notice = f"✅ 索引已重建：{n_files} 个文件 → {n_chunks} 个 chunk"
                except Exception as e:
                    st.session_state.ingest_notice = f"❌ 建库失败：{e}"
            st.rerun()

    if st.session_state.ingest_notice:
        st.info(st.session_state.ingest_notice)
        # 展示一次就清（避免刷屏）
        st.session_state.ingest_notice = None

    st.divider()

    # ---------- 记忆状态 ----------
    st.subheader("🧠 对话记忆")
    stats = st.session_state.agent.memory_stats()
    st.caption(
        f"{stats['n_messages']} 条消息 · {stats['chars']} 字符 / {stats['trigger_chars']} 触发压缩"
    )
    # 进度条：占了压缩阈值的百分之多少
    ratio = min(stats["chars"] / max(stats["trigger_chars"], 1), 1.0)
    st.progress(ratio)
    st.caption(f"累计消耗 tokens: {st.session_state.session_tokens}")

    if st.button("🧹 清空对话历史", use_container_width=True):
        st.session_state.agent.clear_memory()
        st.session_state.history = []
        st.session_state.session_tokens = 0
        st.rerun()

    st.divider()
    st.caption("Day 6 · [GitHub](https://github.com/Gip886/agents)")


# ================================================================
# 主区：对话
# ================================================================

st.title("🤖 知识助手 v3")
st.caption("基于你私人笔记的问答助手 · RAG + Tool Use + 记忆管理")

# ---------- 渲染历史消息 ----------

def render_turn_trace(turn: TurnResult):
    """把 TurnResult 里的工具调用轨迹渲染成可展开的 st.status 卡片"""
    for r in turn.rounds:
        if not r.tool_calls:
            continue
        tool_names = ", ".join(tc.name for tc in r.tool_calls)
        with st.status(
            f"第 {r.round_num} 轮 · 调用工具：{tool_names}",
            state="complete",
            expanded=False,
        ):
            for tc in r.tool_calls:
                st.markdown(f"**🔧 `{tc.name}`**")
                st.code(tc.arguments or "{}", language="json")
                st.markdown("**返回：**")
                st.code(tc.result, language="text")

    # 底部统计
    st.caption(
        f"📊 {len(turn.rounds)} 轮 LLM · {turn.total_tool_calls} 次工具调用 · {turn.total_tokens} tokens"
    )

    if turn.compression_event:
        e = turn.compression_event
        st.info(
            f"🧠 **记忆压缩**：{e['before_msgs']} 条 / {e['before_chars']} 字符 → "
            f"{e['after_msgs']} 条 / {e['after_chars']} 字符\n\n"
            f"摘要预览: {e['summary_preview']}"
        )


for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("turn"):
            render_turn_trace(msg["turn"])


# ---------- 用户输入 ----------

user_input = st.chat_input("问问你的笔记 …（例如：「我笔记里 Go 错误处理怎么讲的？」）")

if user_input:
    # 立即渲染用户消息
    st.session_state.history.append({"role": "user", "content": user_input, "turn": None})
    with st.chat_message("user"):
        st.markdown(user_input)

    # 跑 Agent（有 spinner）
    with st.chat_message("assistant"):
        with st.spinner("🤔 思考中…"):
            start = time.time()
            try:
                result: TurnResult = st.session_state.agent.run_turn(user_input)
            except Exception as e:
                st.error(f"❌ Agent 执行失败：{e}")
                st.stop()
            elapsed = time.time() - start

        st.markdown(result.answer)
        render_turn_trace(result)
        st.caption(f"⏱️ 耗时 {elapsed:.1f}s")

    st.session_state.history.append({
        "role": "assistant",
        "content": result.answer,
        "turn": result,
    })
    st.session_state.session_tokens += result.total_tokens

    # 触发一次 rerun 让侧栏的记忆状态刷新
    st.rerun()
