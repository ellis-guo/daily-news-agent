"""
regex_filter.py — 热点正则过滤 + 来源权重截取
filter_trends(raw, n) -> List[dict]
"""
import re

# 黑名单关键词（命中任意一个即丢弃）
BLACKLIST = [
    # 娱乐/明星
    r"选秀", r"出道", r"演唱会", r"恋爱", r"离婚", r"出轨", r"粉丝", r"爱豆",
    r"明星", r"网红", r"综艺", r"真人秀", r"偶像",
    # 体育
    r"夺冠", r"世界杯", r"奥运", r"赛季", r"球队", r"球员", r"联赛", r"冠军赛",
    # 低价值
    r"星座", r"鸡汤", r"养生", r"减肥", r"美容",
]

BLACKLIST_RE = re.compile("|".join(BLACKLIST))

# 来源权重（值越大优先级越高）
PLATFORM_WEIGHT = {
    "zhihu":            3,
    "weibo":            2,
    "wallstreetcn-hot": 2,
    "baidu":            1,
    "toutiao":          1,
}

# 标题相似度去重（前 N 个字符）
DEDUP_CHARS = 10


def _normalize(title: str) -> str:
    return re.sub(r"[^\w]", "", title)[:DEDUP_CHARS]


def filter_trends(raw: list[dict], n: int = 10) -> list[dict]:
    """
    raw: [{"title", "url", "platform", "rank"}, ...]
    返回过滤 + 截取后的列表（最多 n 条）
    """
    # Step1: 黑名单过滤
    passed = [item for item in raw if not BLACKLIST_RE.search(item["title"])]

    # Step2: 按来源权重排序（weight 降序，rank 升序）
    passed.sort(key=lambda x: (-PLATFORM_WEIGHT.get(x["platform"], 0), x.get("rank", 999)))

    # Step3: 标题相似度去重（跨平台同话题只保留最高权重的一条）
    seen_fp: set[str] = set()
    deduped = []
    for item in passed:
        fp = _normalize(item["title"])
        if fp not in seen_fp:
            seen_fp.add(fp)
            deduped.append(item)

    return deduped[:n]
