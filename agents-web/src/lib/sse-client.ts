/**
 * Client-side SSE 消费器
 * fetch 一个 SSE 端点，按行解析 `data: {...}\n\n`，为每条 event 调 onEvent。
 */
export async function consumeSSE<TEvent>(
  url: string,
  init: RequestInit,
  onEvent: (event: TEvent) => void,
): Promise<void> {
  const resp = await fetch(url, init);
  if (!resp.ok || !resp.body) {
    throw new Error(`SSE ${url} failed: ${resp.status} ${await resp.text().catch(() => "")}`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });

    // SSE 消息以空行分隔
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      // 只关心 data: 行；忽略 event: 之类
      const dataLines: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("data: ")) dataLines.push(line.slice(6));
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
      }
      if (dataLines.length === 0) continue;
      const raw = dataLines.join("\n");
      if (raw === "" || raw === "{}") continue;
      try {
        const evt = JSON.parse(raw) as TEvent;
        onEvent(evt);
      } catch {
        // 静默忽略坏包
      }
    }
  }
}
