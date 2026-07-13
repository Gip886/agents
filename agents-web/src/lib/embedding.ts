/**
 * 火山方舟 multimodal embedding API 封装
 * 对齐 day7/ark_embedding.py
 */
import {
  ARK_API_KEY,
  ARK_BASE_URL,
  ARK_EMBEDDING_ENDPOINT_ID,
} from "./config";

/**
 * 把一批文本转成向量。逐条调 API（Ark multimodal embedding 每次只吃一条 input）。
 */
export async function embedTexts(texts: string[]): Promise<number[][]> {
  if (!ARK_API_KEY) throw new Error("环境变量 ARK_API_KEY 未设置");
  if (!ARK_EMBEDDING_ENDPOINT_ID)
    throw new Error("环境变量 ARK_EMBEDDING_ENDPOINT_ID 未设置");

  const url = `${ARK_BASE_URL}/embeddings/multimodal`;
  const headers = {
    Authorization: `Bearer ${ARK_API_KEY}`,
    "Content-Type": "application/json",
  };

  const results: number[][] = [];
  for (const text of texts) {
    const resp = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify({
        model: ARK_EMBEDDING_ENDPOINT_ID,
        input: [{ type: "text", text }],
        encoding_format: "float",
      }),
    });
    if (!resp.ok) {
      const errText = await resp.text();
      throw new Error(`Embedding API ${resp.status}: ${errText.slice(0, 300)}`);
    }
    const data = await resp.json();
    // 兼容两种响应结构（对齐 Python 版的分支）
    let embedding: number[] | undefined;
    if (data?.data && !Array.isArray(data.data) && data.data.embedding) {
      embedding = data.data.embedding;
    } else if (Array.isArray(data?.data) && data.data.length > 0) {
      embedding = data.data[0].embedding;
    }
    if (!embedding) {
      throw new Error(`未知的响应结构：${JSON.stringify(data).slice(0, 300)}`);
    }
    results.push(embedding);
  }
  return results;
}

export async function embedOne(text: string): Promise<number[]> {
  const [v] = await embedTexts([text]);
  return v;
}
