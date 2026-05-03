"""
Article dataclass — 统一数据模型
"""
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Article:
    id: str                   # md5(url)[:8]
    title: str
    url: str
    source: str               # "36氪" / "Anthropic Engineering" 等
    block: str                # "trend" / "frontier" / "news"
    published: datetime
    summary: str = ""
    full_content_path: str = ""   # 本地路径，不存正文本体
