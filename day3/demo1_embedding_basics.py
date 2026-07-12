"""
Demo 1: 玩玩 Embedding（Doubao-embedding-vision 版本）
========================================
目标：直观感受"向量相似度"。

注意：Doubao-embedding-vision 用 /embeddings/multimodal 端点，
OpenAI SDK 不支持，我们用自己写的 ark_embedding.embed_texts。
"""
import math
from dotenv import load_dotenv
from ark_embedding import embed_texts

load_dotenv()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """余弦相似度：a·b / (|a|·|b|)。范围 [-1, 1]，越接近 1 越像。"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b)


# ---------- 一组测试文本 ----------
texts = [
    "Agent 是能自主决策的智能程序",
    "AI 助手可以理解意图并调用工具",
    "今天中午吃什么好",
    "向量数据库支持语义搜索",
    "The quick brown fox jumps over the lazy dog",
]

print("=" * 60)
print("🧬 生成 embedding")
print("=" * 60)

# 一次批量生成（内部会循环调用 API）
vectors = embed_texts(texts)

for i, (text, vec) in enumerate(zip(texts, vectors), 1):
    print(f"\n📝 文本 {i}: {text}")
    print(f"   向量维度: {len(vec)}")
    print(f"   前 5 维: {[round(x, 4) for x in vec[:5]]}")


print("\n" + "=" * 60)
print("📐 两两余弦相似度")
print("=" * 60)
print(f"\n{'':^4}", end="")
for i in range(len(texts)):
    print(f"  文本{i+1:<5}", end="")
print()

for i in range(len(texts)):
    print(f"文本{i+1}", end="")
    for j in range(len(texts)):
        sim = cosine_similarity(vectors[i], vectors[j])
        if i == j:
            marker = "  ---   "
        elif sim > 0.7:
            marker = f" 🟢{sim:.3f}"
        elif sim > 0.5:
            marker = f" 🟡{sim:.3f}"
        else:
            marker = f" 🔴{sim:.3f}"
        print(marker, end="")
    print()

print("\n" + "=" * 60)
print("💡 观察点")
print("=" * 60)
print("""
1. 文本1（Agent）和 文本2（AI 助手）用词不同，但语义相近 → 相似度高
2. 文本4（向量数据库）和 文本1/2 也有一定相关性（都是 AI 领域）
3. 文本3（吃什么）和其他都不相关 → 相似度都低
4. 文本5（英文）跟中文文本的相似度也应该都低（都是不相关内容）
""")
