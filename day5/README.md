# Day 5 · 记忆增强 + 打标签 / 摘要工具

> 📖 **详细教程**：[docs/day5.html](../docs/day5.html) 或访问 [GitHub Pages 网站](https://gip886.github.io/agents/day5.html)

## 🎯 目标

给 Day 4 的知识助手加两个"长期能用"的关键能力：
1. **对话历史自动压缩** —— 聊很久也不爆 token
2. **写入类工具** —— Agent 反过来帮你整理笔记（打标签、生成摘要）

## 📋 任务清单

- [x] 装依赖、复制 `.env`
- [x] 跑 `python ingest.py` 建库（新增 frontmatter 剥离逻辑）
- [x] 跑 `python agent.py` 开始对话
- [x] 至少体验：只读 + summarize_note + add_tag + list_tags
- [x] 观察记忆压缩事件（长对话时自动触发）

## 🚀 快速开始

```bash
cd day5

# 沿用 day4 的 venv 也行，或者重建
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp ../day4/.env .env

# 建库
python ingest.py

# 开始对话
python agent.py
```

## 📁 项目结构

```
day5/
├── ark_embedding.py     # embedding HTTP（Day 3 复用）
├── frontmatter.py       # 🆕 极简 YAML frontmatter 解析器
├── memory.py            # 🆕 对话记忆：滑窗 + 自动摘要
├── knowledge_base.py    # 扩展：剥 frontmatter + read/update_meta
├── tools.py             # 扩展：加 add_tag / summarize_note / list_tags
├── agent.py             # 集成 ConversationMemory
├── ingest.py            # 建库脚本（不变）
├── notes/               # 你的笔记（.md 文件）
└── chroma_db/           # 向量库（gitignore）
```

## 🛠️ 6 个工具

| 工具 | 类型 | 何时用 |
|------|------|--------|
| `search_notes(query, top_k)` | 只读 | 语义找片段 |
| `read_full_note(filename)` | 只读 | 读整篇原文 |
| `list_notes()` | 只读 | 列出文件名 |
| `list_tags()` | 只读 | 列所有笔记的 tags/summary |
| `add_tag(filename, tags)` | ✏️ 写入 | 加标签，写回 frontmatter |
| `summarize_note(filename)` | ✏️ 写入 | 让 LLM 生成摘要并保存 |

## 💬 推荐提问

```
你: 我笔记里 Go 的错误处理是怎么讲的？          # 只读能力不回退
你: 给 go-tips.md 生成一份摘要并保存              # summarize_note
你: 给 rag-notes.md 加两个标签：rag 和 embedding  # add_tag
你: 现在我笔记有哪些主题？                        # list_tags
你: 继续聊多几轮 …… 观察 🧠 [记忆压缩] 事件
```

## 🧠 核心概念

- **YAML frontmatter**：元数据跟着数据走，git diff 友好，工具通用
- **ConversationMemory**：只在 `role="user"` 处切分（避免拆散 tool_calls）
- **ToolContext**：给写入工具注入 LLM client，比全局变量干净
- **写入工具 = 危险的**：System prompt 里明确"用户没说保存就别调"

## ✅ 完成后

```bash
git add day5/
git commit -m "Day 5: 记忆增强 + 打标签/摘要"
git push
```
