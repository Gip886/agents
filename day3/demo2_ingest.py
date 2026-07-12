"""
Demo 2: Ingest 流水线（Doubao-embedding-vision 版本）
========================================
把 notes/*.md 切分 → embedding → 存 ChromaDB

跑法：
    python demo2_ingest.py
"""
import glob
from pathlib import Path

import chromadb
from dotenv import load_dotenv

from ark_embedding import embed_texts

load_dotenv()

# ---------- 配置 ----------
NOTES_DIR = "notes"
CHROMA_DIR = "chroma_db"
COLLECTION_NAME = "knowledge"
CHUNK_MAX_CHARS = 500       # 每块最大字符数
CHUNK_OVERLAP = 50          # 相邻块重叠字符数


def split_text(text: str, max_chars: int = CHUNK_MAX_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """按段落切，段落太长时用滑动窗口切并保留 overlap 重叠。"""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks = []
    for para in paragraphs:
        if len(para) <= max_chars:
            chunks.append(para)
        else:
            start = 0
            while start < len(para):
                end = start + max_chars
                chunks.append(para[start:end])
                if end >= len(para):
                    break
                start = end - overlap

    return chunks


def main():
    print(f"📂 Chroma 存储路径: ./{CHROMA_DIR}/")
    chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)

    # 每次跑先删除旧的 collection，方便迭代
    try:
        chroma_client.delete_collection(COLLECTION_NAME)
        print(f"🧹 已清空旧的 collection: {COLLECTION_NAME}")
    except Exception:
        pass

    collection = chroma_client.create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "个人笔记向量库"},
    )

    md_files = sorted(glob.glob(f"{NOTES_DIR}/*.md"))
    if not md_files:
        print(f"❌ {NOTES_DIR}/ 下没有找到 .md 文件")
        return

    print(f"\n📁 找到 {len(md_files)} 个笔记文件")

    all_ids: list[str] = []
    all_texts: list[str] = []
    all_metadatas: list[dict] = []

    for md_file in md_files:
        text = Path(md_file).read_text(encoding="utf-8")
        chunks = split_text(text)
        print(f"   ├─ {md_file:<40} → {len(chunks)} chunks")

        for idx, chunk in enumerate(chunks):
            chunk_id = f"{md_file}#{idx}"
            all_ids.append(chunk_id)
            all_texts.append(chunk)
            all_metadatas.append({
                "file": md_file,
                "chunk_idx": idx,
            })

    print(f"\n🧬 生成 embedding：{len(all_texts)} 段...")
    print("   （vision 端点只能单条调用，会看到逐条进度）")

    # 分批处理并显示进度
    BATCH_SIZE = 8
    all_embeddings: list[list[float]] = []
    for i in range(0, len(all_texts), BATCH_SIZE):
        batch = all_texts[i:i + BATCH_SIZE]
        vecs = embed_texts(batch)
        all_embeddings.extend(vecs)
        print(f"   完成 {min(i + BATCH_SIZE, len(all_texts))}/{len(all_texts)}")

    collection.add(
        ids=all_ids,
        documents=all_texts,
        embeddings=all_embeddings,
        metadatas=all_metadatas,
    )

    print(f"\n✅ 入库完成：{len(all_ids)} 个 chunk 存入 ChromaDB")
    print(f"📊 collection.count() = {collection.count()}")
    print(f"\n下一步：跑 python demo3_query.py 试试检索")


if __name__ == "__main__":
    main()
