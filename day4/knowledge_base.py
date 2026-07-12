"""
知识库访问层
====================================
封装 ChromaDB 的读写。
把"存储细节"和"业务代码"分开 —— 上层（tools.py）只跟这个接口打交道。

好处：以后想从 Chroma 换成 pgvector / Qdrant，只改这一个文件。
"""
import os
import glob
from pathlib import Path

import chromadb

from ark_embedding import embed_texts, embed_one


CHROMA_DIR = "chroma_db"
COLLECTION_NAME = "knowledge"
NOTES_DIR = "notes"

# Chunking 参数
CHUNK_MAX_CHARS = 500
CHUNK_OVERLAP = 50


# ================================================================
# 文本切分
# ================================================================

def split_text(text: str, max_chars: int = CHUNK_MAX_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """按段落切分，段落太长时滑窗切并保留 overlap 重叠。"""
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


# ================================================================
# ChromaDB 客户端封装
# ================================================================

class KnowledgeBase:
    def __init__(self, chroma_dir: str = CHROMA_DIR, collection_name: str = COLLECTION_NAME):
        self.client = chromadb.PersistentClient(path=chroma_dir)
        self.collection_name = collection_name
        self._collection = None

    @property
    def collection(self):
        """懒加载 collection（读操作）"""
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(self.collection_name)
        return self._collection

    # ---------- 建库 ----------

    def rebuild(self, notes_dir: str = NOTES_DIR, batch_size: int = 8):
        """
        清空并重建 collection。
        读取 notes_dir 下所有 .md，切分，embedding，入库。
        返回 (文件数, chunk 数)
        """
        # 先删旧
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:
            pass
        self._collection = self.client.create_collection(
            name=self.collection_name,
            metadata={"description": "个人笔记向量库"},
        )

        md_files = sorted(glob.glob(f"{notes_dir}/*.md"))
        if not md_files:
            raise RuntimeError(f"{notes_dir}/ 下没有找到 .md 文件")

        all_ids: list[str] = []
        all_texts: list[str] = []
        all_metadatas: list[dict] = []

        for md_file in md_files:
            text = Path(md_file).read_text(encoding="utf-8")
            filename = os.path.basename(md_file)   # 只存文件名，不带路径
            chunks = split_text(text)
            print(f"   ├─ {filename:<30} → {len(chunks)} chunks")

            for idx, chunk in enumerate(chunks):
                all_ids.append(f"{filename}#{idx}")
                all_texts.append(chunk)
                all_metadatas.append({"file": filename, "chunk_idx": idx})

        print(f"\n🧬 生成 embedding：{len(all_texts)} 段...")
        all_embeddings: list[list[float]] = []
        for i in range(0, len(all_texts), batch_size):
            batch = all_texts[i:i + batch_size]
            vecs = embed_texts(batch)
            all_embeddings.extend(vecs)
            print(f"   完成 {min(i + batch_size, len(all_texts))}/{len(all_texts)}")

        self._collection.add(
            ids=all_ids,
            documents=all_texts,
            embeddings=all_embeddings,
            metadatas=all_metadatas,
        )
        return len(md_files), len(all_ids)

    # ---------- 查询 ----------

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        """
        语义检索。
        返回：[{text, file, chunk_idx, similarity}, ...]
        """
        vec = embed_one(query)
        result = self.collection.query(
            query_embeddings=[vec],
            n_results=top_k,
        )
        docs = result["documents"][0]
        distances = result["distances"][0]
        metadatas = result["metadatas"][0]

        return [
            {
                "text": doc,
                "file": meta["file"],
                "chunk_idx": meta["chunk_idx"],
                "similarity": round(1 / (1 + dist), 3),   # 距离转相似度
            }
            for doc, dist, meta in zip(docs, distances, metadatas)
        ]

    # ---------- 读全文 ----------

    def read_full_note(self, filename: str, notes_dir: str = NOTES_DIR, max_chars: int = 8000) -> str:
        """
        读整篇笔记原文。
        如果文件不存在，抛 FileNotFoundError。
        如果文件过长，截断并标注。
        """
        path = os.path.join(notes_dir, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(f"笔记不存在：{filename}")

        text = Path(path).read_text(encoding="utf-8")
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n[...原文过长已截断，总长 {len(text)} 字符，仅展示前 {max_chars} 字符]"
        return text

    # ---------- 列出所有笔记 ----------

    def list_notes(self, notes_dir: str = NOTES_DIR) -> list[str]:
        """返回 notes/ 下所有 .md 文件名（不含路径）"""
        md_files = sorted(glob.glob(f"{notes_dir}/*.md"))
        return [os.path.basename(f) for f in md_files]
