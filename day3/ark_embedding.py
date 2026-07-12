"""
Doubao-embedding-vision 的封装模块
====================================
Vision embedding 用的是 /embeddings/multimodal 端点，跟 OpenAI 的标准
embedding API 不一样，所以我们直接用 httpx 发 HTTP 请求。

对外暴露一个 embed_texts(texts) 函数，行为跟 OpenAI 的 embeddings.create 一样。
"""
import os
import httpx


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    把一批文本转成向量。
    调用火山方舟的 multimodal embedding API（Doubao-embedding-vision）。

    参数:
        texts: 文本列表
    返回:
        每个文本对应一个 float 向量组成的列表
    """
    api_key = os.getenv("ARK_API_KEY")
    base_url = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    model = os.getenv("ARK_EMBEDDING_ENDPOINT_ID")

    if not api_key:
        raise RuntimeError("环境变量 ARK_API_KEY 未设置")
    if not model:
        raise RuntimeError("环境变量 ARK_EMBEDDING_ENDPOINT_ID 未设置")

    url = f"{base_url}/embeddings/multimodal"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    results: list[list[float]] = []
    # Multimodal API 每次只处理一条 input，所以我们循环
    with httpx.Client(timeout=60.0) as client:
        for text in texts:
            payload = {
                "model": model,
                "input": [
                    # multimodal 格式：input 是内容块数组
                    # 我们只用文本块（不传图片）
                    {"type": "text", "text": text},
                ],
                "encoding_format": "float",
            }
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Embedding API 返回 {resp.status_code}: {resp.text}"
                )
            data = resp.json()

            # 兼容两种可能的响应格式
            #   A: {"data": {"embedding": [...]}}
            #   B: {"data": [{"embedding": [...]}]}
            payload_data = data.get("data")
            if isinstance(payload_data, dict) and "embedding" in payload_data:
                embedding = payload_data["embedding"]
            elif isinstance(payload_data, list) and payload_data:
                embedding = payload_data[0]["embedding"]
            else:
                raise RuntimeError(f"未知的响应结构：{data}")

            results.append(embedding)

    return results


def embed_one(text: str) -> list[float]:
    """便捷方法：只需要一条文本时用这个。"""
    return embed_texts([text])[0]
