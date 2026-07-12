# Day 4 · 组装：知识助手 v1

> 📖 **详细教程**：[docs/day4.html](../docs/day4.html) 或访问 [GitHub Pages 网站](https://gip886.github.io/agents/day4.html)

## 🎯 目标

融合 Day 2（Tool Use）+ Day 3（RAG），做出真正能用的知识助手。

## 📋 任务清单

- [x] 装依赖、复制 `.env`
- [x] 把笔记放进 `notes/` 目录
- [x] 跑 `python ingest.py` 建库
- [x] 跑 `python agent.py` 开始对话
- [x] 至少体验 3 种不同工具组合（简单查询、多次检索、需读全文）
- [x] 观察 Agent 打印的"思考轨迹"

## 🚀 快速开始

```bash
cd day4

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 复用 Day 3 的 .env
cp ../day3/.env .env

# 用 Day 3 的示例笔记（或换成你自己的）
mkdir -p notes
cp ../day3/notes/*.md notes/

# 建库
python ingest.py

# 开始对话
python agent.py
```

## 📁 项目结构

```
day4/
├── ark_embedding.py     # embedding HTTP 封装
├── knowledge_base.py    # ChromaDB 访问层
├── tools.py             # 工具集（schema + 实现）
├── agent.py             # Agent 主循环
├── ingest.py            # 建库脚本
├── notes/               # 你的笔记
└── chroma_db/           # 向量库（gitignore）
```

## 🎯 3 个工具

| 工具 | 作用 | 何时使用 |
|------|------|---------|
| `search_notes` | 语义检索片段 | 用户问"我笔记里说了啥" |
| `read_full_note` | 读整篇原文 | 片段不完整、需要全貌 |
| `list_notes` | 列所有笔记 | 用户问有哪些、Agent 需要看有啥文件 |

## 💬 推荐提问顺序

```
你: 我笔记里 Go 的错误处理是怎么讲的？          # 一次 search 就够
你: 帮我总结一下 rag-notes.md 这篇笔记           # search + read_full_note
你: goroutine 之间怎么通信？                    # 关键词不匹配，考验语义
你: 我笔记里都讲了 Agent 的哪些方面？            # 可能多次 search
你: 你好，介绍下自己                            # 不用工具
你: 我笔记里有讲区块链吗？                      # 应该老实说没有
```

## 🧠 核心概念

- **多层架构**：`ark_embedding` → `knowledge_base` → `tools` → `agent`
- **工具描述是灵魂**：LLM 完全靠 description 决定用啥工具
- **相似度分数是信号**：Agent 看到低相似度就知道要老实说"没找到"
- **System Prompt 是教练**：约束 Agent 行为、要求引用来源

## ✅ 完成后

```bash
git add day4/
git commit -m "Day 4: 知识助手 v1"
git push
```
