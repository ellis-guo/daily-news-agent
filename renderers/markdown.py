"""
markdown.py — 生成 MD 文件，唯一知道 MD 格式的模块
write(sections, path, status)
read_by_index(path, n) -> dict | None
"""
from pathlib import Path

SECTION_TITLES = {
    "trend":    "一、热点",
    "news":     "二、综合新闻",
    "frontier": "三、大厂前沿",
}

BLOCK_ORDER = ["trend", "news", "frontier"]


def write(sections: dict, path: Path, status: dict = None):
    """
    sections: {"trend": [Article, ...], "frontier": [...], "news": [...]}
    status:   pipeline_status.json 的 modules 字典（可选，用于写错误板块）
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    today = path.stem  # YYYY-MM-DD

    lines = [f"# {today} 新闻摘要\n"]
    n = 1       # 数字编号（trend + news）
    f_idx = 0   # frontier 字母编号索引

    for block in BLOCK_ORDER:
        articles = sections.get(block, [])
        if not articles:
            continue

        lines.append(f"## {SECTION_TITLES[block]}\n")
        for article in articles:
            if block == "frontier":
                label = chr(ord('A') + f_idx)
                lines.append(f"### {label}. 【{article.source}】{article.title}")
                f_idx += 1
            else:
                lines.append(f"### {n}. 【{article.source}】{article.title}")
                n += 1
            if article.summary:
                lines.append(article.summary[:300])
            if article.url:
                lines.append(f"🔗 {article.url} ({block})")
            if article.full_content_path:
                key = Path(article.full_content_path).stem
                lines.append(f"📄 {key}")
            lines.append("")

    # 模块异常 / 无内容板块
    if status:
        modules = status.get("modules", {})
        errors = [(k, v["error"]) for k, v in modules.items() if v.get("error")]
        empty = [k for k, v in modules.items() if v.get("count", 1) == 0 and not v.get("error")]

        if errors:
            lines.append("## ❌ 模块异常\n")
            for mod, err in errors:
                lines.append(f"- {mod}: {err}")
            lines.append("")

        if empty:
            lines.append("## ⚠️ 今日无内容\n")
            for mod in empty:
                lines.append(f"- {mod}")
            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def read_by_index(path: Path, n) -> dict | None:
    """
    从 MD 文件里按编号取出对应条目信息。
    n 可以是数字（trend/news）或字母字符串如 'A'（frontier）。
    返回 {title, url, source, block, article_key} 或 None。
    """
    if not path.exists():
        return None

    import re
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()

    current_block = None
    for i, line in enumerate(lines):
        for block, title in SECTION_TITLES.items():
            if f"## {title}" in line:
                current_block = block
                break

        # 字母编号（frontier）
        if isinstance(n, str) and n.isalpha():
            m = re.match(rf"^### {n.upper()}\. 【([^】]+)】(.+)$", line)
        else:
            m = re.match(rf"^### {n}\. 【([^】]+)】(.+)$", line)

        if m:
            source = m.group(1)
            title_text = m.group(2)
            url = ""
            article_key = ""

            for j in range(i + 1, min(i + 6, len(lines))):
                url_m = re.match(r"🔗 (\S+) \((\w+)\)", lines[j])
                if url_m:
                    url = url_m.group(1)
                key_m = re.match(r"📄 (\S+)", lines[j])
                if key_m:
                    article_key = key_m.group(1)

            return {
                "title": title_text,
                "url": url,
                "source": source,
                "block": current_block,
                "article_key": article_key,
            }

    return None
