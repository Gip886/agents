"""
Doubao-embedding-vision 的封装模块（从 Day 3 拷贝，无改动）
"""
import os
import httpx


def embed_texts(texts: list[str]) -> list[list[float]]:
    """把一批文本转成向量。逐条调用 multimodal API。"""
    api_key = os.getenv("ARK_API_KEY")
    base_url = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    model = os.getenv("ARK_EMBEDDING_ENDPOINT_ID")

    if not api_key:
        raise RuntimeError("环境变量 ARK_API_KEY 未设置")
    if not model:
        raise RuntimeError("环境变量 ARK_EMBEDDING_ENDPOINT_ID 未设置")

    url = f"{base_url}/embeddings/multimodal"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    results: list[list[float]] = []
    with httpx.Client(timeout=60.0) as client:
        for text in texts:
            payload = {
                "model": model,
                "input": [{"type": "text", "text": text}],
                "encoding_format": "float",
            }
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"Embedding API {resp.status_code}: {resp.text}")
            data = resp.json()
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
    return embed_texts([text])[0]
