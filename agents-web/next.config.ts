import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 显式锚定 workspace root 到当前项目 —— 否则 Next 会往上走找到
  // ~/yarn.lock 把 standalone 打成 Documents/practice/agents/agents-web/... 的绝对路径结构
  outputFileTracingRoot: path.join(__dirname),
  turbopack: {
    root: path.join(__dirname),
  },

  // 自包含产物：build 后 .next/standalone 里带一份精简 node_modules，
  // 用户 `node server.js` 直接起，不需要在目标机器上跑 npm install。
  output: "standalone",

  // better-sqlite3 是原生模块，Next 追踪外部依赖时不要打进 bundle
  serverExternalPackages: ["better-sqlite3"],
};

export default nextConfig;
