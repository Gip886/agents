"""
极简 YAML frontmatter 解析器
====================================
用来在 .md 笔记开头存 tags 和 summary，格式：

    ---
    tags: [go, error-handling, backend]
    summary: Go 用返回值传错误，errors.Is / errors.As 判断具体类型。
    ---
    # Go 学习备忘
    ...

不引入 PyYAML —— 只支持我们需要的 3 种值：字符串、列表[str]、多行字符串（| 起头）。
"""
from __future__ import annotations

import re


FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def parse(text: str) -> tuple[dict, str]:
    """
    从文本头部解析 frontmatter，返回 (meta_dict, body_without_frontmatter)。
    没有 frontmatter 就返回 ({}, text) 原样。
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text

    fm_text = m.group(1)
    body = text[m.end():]

    meta: dict = {}
    current_key = None
    for raw_line in fm_text.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue

        # 缩进行 = 多行值的延续（简化：这里不支持）
        # key: value 或 key: [a, b] 或 key: value with spaces
        if ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            current_key = key
            if value.startswith("[") and value.endswith("]"):
                items = value[1:-1].split(",")
                meta[key] = [x.strip().strip("'\"") for x in items if x.strip()]
            elif value == "":
                meta[key] = ""
            else:
                # 剥单引号或双引号
                if (value.startswith('"') and value.endswith('"')) or (
                    value.startswith("'") and value.endswith("'")
                ):
                    value = value[1:-1]
                meta[key] = value
    return meta, body


def dump(meta: dict, body: str) -> str:
    """
    把 meta + body 拼回带 frontmatter 的文本。空 meta 时不加 frontmatter。
    """
    if not meta:
        # 但如果 body 里之前有 frontmatter，我们已经在 parse 阶段剥掉了 —— 这里就是"清空"
        return body

    lines = ["---"]
    for key, value in meta.items():
        if isinstance(value, list):
            joined = ", ".join(value)
            lines.append(f"{key}: [{joined}]")
        elif isinstance(value, str) and ("\n" in value or ":" in value or "#" in value):
            # 含特殊字符的字符串加引号
            escaped = value.replace('"', '\\"').replace("\n", " ")
            lines.append(f'{key}: "{escaped}"')
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")  # 空行分隔 body

    # 如果 body 不以换行开头，加一个
    if not body.startswith("\n"):
        return "\n".join(lines) + body
    return "\n".join(lines) + body


def strip(text: str) -> str:
    """便捷函数：只要 body 部分"""
    _, body = parse(text)
    return body
