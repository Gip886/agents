"""
建库脚本
====================================
读取 notes/ 下所有 .md，切分入库到 chroma_db/。

跑法：
    python ingest.py

每次跑会先清空旧数据。
"""
from dotenv import load_dotenv

from knowledge_base import KnowledgeBase, CHROMA_DIR

load_dotenv()


def main():
    print(f"📂 Chroma 存储路径: ./{CHROMA_DIR}/")
    kb = KnowledgeBase()

    print("📁 开始扫描 notes/...")
    n_files, n_chunks = kb.rebuild()

    print(f"\n✅ 入库完成：{n_files} 个文件 → {n_chunks} 个 chunk")
    print(f"\n下一步：跑 python agent.py 试试知识助手")


if __name__ == "__main__":
    main()
