"""
Demo 3: 语义检索（Doubao-embedding-vision 版本）
========================================
在 Demo 2 已经入库的基础上，做语义搜索。

跑法：
    python demo3_query.py
"""
import chromadb
from dotenv import load_dotenv

from ark_embedding import embed_one

load_dotenv()

CHROMA_DIR = "chroma_db"
COLLECTION_NAME = "knowledge"
TOP_K = 3


def search(collection, query: str, top_k: int = TOP_K):
    """输入问题 → 转向量 → Chroma 检索 top_k → 打印"""
    query_vec = embed_one(query)

    results = collection.query(
        query_embeddings=[query_vec],
        n_results=top_k,
    )

    ids = results["ids"][0]
    docs = results["documents"][0]
    distances = results["distances"][0]
    metadatas = results["metadatas"][0]

    print(f"\n🔍 检索: \"{query}\"\n")

    for i, (doc, dist, meta) in enumerate(zip(docs, distances, metadatas), 1):
        similarity = 1 / (1 + dist)
        preview = doc[:150].replace("\n", " ")
        print(f"  [{i}] 相似度 {similarity:.3f}  |  距离 {dist:.3f}  |  来源: {meta['file']}#{meta['chunk_idx']}")
        print(f"      {preview}{'...' if len(doc) > 150 else ''}\n")


def main():
    chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
    try:
        collection = chroma_client.get_collection(COLLECTION_NAME)
    except Exception:
        print(f"❌ collection '{COLLECTION_NAME}' 不存在。请先跑 python demo2_ingest.py")
        return

    print(f"✅ 已加载 collection: {COLLECTION_NAME}（{collection.count()} 个 chunk）")
    print("=" * 60)
    print("💬 输入问题开始检索（输入 'exit' 退出）")

    sample_queries = [
        "Agent 是怎么记住上下文的？",
        "Go 里怎么处理错误",
        "什么是向量数据库",
    ]
    print("\n💡 示例问题（可以试试）：")
    for q in sample_queries:
        print(f"   - {q}")
    print("=" * 60)

    while True:
        try:
            query = input("\n❓ 问题: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 再见！")
            break

        if query.lower() == "exit":
            print("👋 再见！")
            break
        if not query:
            continue

        search(collection, query)


if __name__ == "__main__":
    main()
