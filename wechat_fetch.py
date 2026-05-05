#!/usr/bin/env python3
"""
Step4: 微信公众号全文抓取（v4）
- 读今日 digest MD，找出所有 综合新闻 板块里的公众号条目（mp.weixin.qq.com）
- 用 lite.py 抓全文（纯文字，不下载图片）
- 存到 ~/.hermes/articles/YYYY-MM-DD/{article_key}.md
- 把前 200 字回填到 digest MD 对应条目（摘要在 🔗 之前，📄 在 🔗 之后）
"""

import asyncio
import hashlib
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

WECHAT_DIR = Path.home() / "wechat-article-to-markdown"
VENV_PYTHON = WECHAT_DIR / ".venv/bin/python"

# 如果当前 python 不是 venv 的，重新用 venv python 跑自己
if sys.executable != str(VENV_PYTHON) and VENV_PYTHON.exists():
    result = subprocess.run([str(VENV_PYTHON), __file__] + sys.argv[1:])
    sys.exit(result.returncode)

# 引入 lite.py
sys.path.insert(0, str(WECHAT_DIR))

CST = timezone(timedelta(hours=8))
HERMES_DIR = Path.home() / ".hermes"
DIGESTS_DIR = HERMES_DIR / "digests"
ARTICLES_DIR = HERMES_DIR / "articles"


def get_article_key(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:8]


def find_wechat_articles(md_path: Path) -> list[dict]:
    """从 MD 文件里找出综合新闻板块里的公众号条目（未处理过的）"""
    articles = []
    content = md_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    in_news_block = False
    i = 0
    while i < len(lines):
        line = lines[i]

        # 板块切换检测
        if line.startswith("## "):
            in_news_block = "二、综合新闻" in line
            i += 1
            continue

        # 只处理综合新闻板块里的条目
        if in_news_block and line.startswith("### ") and "【" in line:
            for j in range(i + 1, min(i + 6, len(lines))):
                # v4 格式：🔗 URL (news)
                m = re.match(r"🔗 (https://mp\.weixin\.qq\.com/\S+) \(news\)", lines[j])
                if m:
                    url = m.group(1)
                    already_done = any(
                        lines[k].startswith("📄 ")
                        for k in range(j + 1, min(j + 3, len(lines)))
                    )
                    if not already_done:
                        articles.append({
                            "title_line_idx": i,
                            "url_line_idx": j,
                            "url": url,
                            "article_key": get_article_key(url),
                        })
                    break
        i += 1

    return articles


async def fetch_article_text(url: str, output_dir: Path) -> str | None:
    """抓取文章，返回纯文字 MD 内容（跳过图片下载）"""
    import httpx
    from lite import (
        extract_content_html, extract_metadata,
        process_content, convert_to_markdown, build_markdown, UA
    )
    from bs4 import BeautifulSoup

    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
            timeout=20.0,
            follow_redirects=True,
        ) as client:
            r = await client.get(url)
            r.raise_for_status()
            html = r.text

        content_html = extract_content_html(html)
        if not content_html:
            print(f"  [WARN] 没找到正文: {url}", file=sys.stderr)
            return None

        soup = BeautifulSoup(html, "html.parser")
        meta = extract_metadata(html, soup)
        meta["source_url"] = url
        if not meta["title"]:
            meta["title"] = "untitled"

        body_html, code_blocks, _ = process_content(content_html)
        md = convert_to_markdown(body_html, code_blocks)
        md = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", md)

        final = build_markdown(meta, md)
        output_dir.mkdir(parents=True, exist_ok=True)
        return final

    except Exception as e:
        print(f"  [WARN] 抓取失败 {url}: {e}", file=sys.stderr)
        return None


def extract_preview(md_content: str, chars: int = 200) -> str:
    """提取 MD 正文前 N 字（跳过 frontmatter 和标题）"""
    lines = md_content.splitlines()
    text_lines = []
    in_header = True
    for line in lines:
        if in_header and (line.startswith("#") or line.startswith(">") or
                          line == "---" or line.strip() == ""):
            continue
        in_header = False
        stripped = line.strip()
        if stripped:
            text_lines.append(stripped)

    return " ".join(text_lines)[:chars]


def backfill_md(md_path: Path, article: dict, preview: str, article_key: str):
    """
    把摘要和 📄 标记回填到 digest MD。
    v4 格式：摘要插在 🔗 行之前，📄 插在 🔗 行之后。
    """
    content = md_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    url_idx = article["url_line_idx"]

    inserts_before = []
    inserts_after = []

    if preview:
        inserts_before.append(preview)
    inserts_after.append(f"📄 {article_key}")

    lines = (
        lines[:url_idx] +
        inserts_before +
        [lines[url_idx]] +
        inserts_after +
        lines[url_idx + 1:]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def main():
    today = datetime.now(CST).strftime("%Y-%m-%d")
    md_path = DIGESTS_DIR / f"{today}.md"

    if not md_path.exists():
        print(f"[ERROR] 今日 MD 不存在: {md_path}", file=sys.stderr)
        sys.exit(1)

    articles = find_wechat_articles(md_path)
    if not articles:
        print("[Done] 今日无公众号文章需要处理", file=sys.stderr)
        return

    print(f"[Step4] 发现 {len(articles)} 篇公众号文章", file=sys.stderr)
    article_dir = ARTICLES_DIR / today
    article_dir.mkdir(parents=True, exist_ok=True)

    success = 0
    for idx, article in enumerate(articles):
        url = article["url"]
        key = article["article_key"]
        out_file = article_dir / f"{key}.md"

        print(f"  [{idx+1}/{len(articles)}] 抓取: {url[:60]}...", file=sys.stderr)

        if out_file.exists():
            print(f"  已存在，跳过: {out_file}", file=sys.stderr)
            success += 1
            continue

        md_content = await fetch_article_text(url, article_dir)
        if not md_content:
            continue

        out_file.write_text(md_content, encoding="utf-8")
        preview = extract_preview(md_content)

        # 重新解析行号（因为前面的 backfill 可能改了行数）
        fresh_articles = find_wechat_articles(md_path)
        match = next((a for a in fresh_articles if a["url"] == url), None)
        if match:
            backfill_md(md_path, match, preview, key)
            print(f"  OK: {out_file.name} | 摘要: {preview[:40]}...", file=sys.stderr)
            success += 1
        else:
            print(f"  [WARN] 回填失败，找不到对应条目: {url}", file=sys.stderr)

        if idx < len(articles) - 1:
            await asyncio.sleep(2)

    print(f"[Done] {success}/{len(articles)} 篇成功，文章存于: {article_dir}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
