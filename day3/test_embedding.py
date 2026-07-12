"""快速验证 vision embedding 可用"""
from dotenv import load_dotenv
from ark_embedding import embed_one, embed_texts

load_dotenv()

print("🔍 测试 1：单条文本")
try:
    vec = embed_one("hello world")
    print(f"✅ 成功！向量维度: {len(vec)}")
    print(f"   前 5 维: {[round(x, 4) for x in vec[:5]]}")
except Exception as e:
    print(f"❌ 失败: {e}")

print("\n🔍 测试 2：批量（2 条）")
try:
    vecs = embed_texts(["今天天气不错", "The weather is nice today"])
    print(f"✅ 成功！拿到 {len(vecs)} 个向量")
    print(f"   每个维度: {len(vecs[0])}")

    # 顺便算一下相似度
    import math
    a, b = vecs[0], vecs[1]
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    sim = dot / (na * nb)
    print(f"   两句话相似度: {sim:.4f}  （中英文同义，应该 > 0.5）")
except Exception as e:
    print(f"❌ 失败: {e}")
