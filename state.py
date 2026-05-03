"""
StateManager — 封装 news_state.json 的去重逻辑
"""
import json
from pathlib import Path

STATE_FILE = Path.home() / ".hermes" / "news_state.json"
MAX_SEEN = 500


class StateManager:
    def __init__(self):
        self._seen: set[str] = set()
        self._ordered: list[str] = []
        self._load()

    def _load(self):
        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text())
                self._ordered = data.get("seen_ids", [])
                self._seen = set(self._ordered)
            except Exception:
                pass

    def is_seen(self, url: str) -> bool:
        return url in self._seen

    def mark_seen(self, url: str):
        if url and url not in self._seen:
            self._seen.add(url)
            self._ordered.append(url)

    def mark_batch(self, urls: list[str]):
        for u in urls:
            self.mark_seen(u)

    def save(self):
        trimmed = self._ordered[-MAX_SEEN:]
        STATE_FILE.write_text(
            json.dumps({"seen_ids": trimmed}, ensure_ascii=False, indent=2)
        )
