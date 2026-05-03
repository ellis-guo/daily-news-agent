"""
markdown.py — 生成 MD 文件，唯一知道 MD 格式的模块
write(sections, path, status)
read_by_index(path, n) -> dict | None
"""
from pathlib import Path

SECTION_TITLES = {
    "trend":    "一、热点",
    "frontier": "二、大厂前沿",
    "news":     "三、综合新闻",
}

BLOCK_ORDER = ["trend", "frontier", "news"]


def write(sections: dict, path: Path, status: dict = None):
    """
    sections: {"trend": [Article, ...], "frontier": [...], "news": [...]}
    status:   pipeline_status.json 的 modules 字典（可选，用于写错误板块）
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    today = path.stem  # YYYY-MM-DD

    lines = [f"# {today} 新闻摘要\n"]
    n = 1  # 全局编号

    for block in BLOCK_ORDER:
        articles = sections.get(block, [])
        if not articles:
            continue

        lines.append(f"## {SECTION_TITLES[block]}\n")
        for article in articles:
            lines.append(f"### {n}. 【{article.source}】{article.title}")
            if article.summary:
                lines.append(article.summary[:300])
            if article.url:
                lines.append(f"🔗 {article.url} ({block})")
            if article.full_content_path:
                # 只存 8 位 key，不存完整路径
                key = Path(article.full_content_path).stem
                lines.append(f"📄 {key}")
            lines.append("")
            n += 1

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


def read_by_index(path: Path, n: int) -> dict | None:
    """
    从 MD 文件里按全局编号取出对应条目信息。
    返回 {"title", "url", "source", "block", "article_key"} 或 None。
    """
    if not path.exists():
        return None

    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()

    current_block = None
    for i, line in enumerate(lines):
        # 检测当前板块
        for block, title in SECTION_TITLES.items():
            if f"## {title}" in line:
                current_block = block
                break

        # 找到目标编号的标题行
        import re
        m = re.match(rf"^### {n}\. 【([^】]+)】(.+)$", line)
        if m:
            source = m.group(1)
            title_text = m.group(2)
            url = ""
            article_key = ""

            # 往下找 🔗 和 📄
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
