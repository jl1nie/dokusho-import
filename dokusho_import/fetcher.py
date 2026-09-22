"""読書メーターへのアクセス。直列・間隔あけ・キャッシュ。

140冊規模の個人利用を想定。同じページを二度取らないことと、
リクエスト間隔を空けることを実装側で強制する。
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_USER_AGENT = (
    "dokusho-import/0.1 (personal bookshelf migration; "
    "contact: set-your-email-here)"
)


class Cache:
    """book_id や URL 単位の取得結果をディスクに置く。

    再実行時に読書メーターへ同じリクエストを投げないため。
    """

    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, str] = {}
        if path.exists():
            self.data = json.loads(path.read_text(encoding="utf-8"))

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def put(self, key: str, value: str) -> None:
        self.data[key] = value
        self.flush()

    def flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False), encoding="utf-8"
        )


class Fetcher:
    def __init__(
        self,
        *,
        cache: Cache | None = None,
        min_interval: float = 2.0,
        jitter: float = 0.5,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: float = 30.0,
    ):
        self.cache = cache
        self.min_interval = min_interval
        self.jitter = jitter
        self.user_agent = user_agent
        self.timeout = timeout
        self._last_request = 0.0
        self.requests_made = 0

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last_request
        delay = self.min_interval - elapsed
        if self._last_request and delay > 0:
            time.sleep(delay + random.uniform(0, self.jitter))

    def get(self, url: str, *, cache_key: str | None = None) -> str:
        key = cache_key or url
        if self.cache is not None:
            cached = self.cache.get(key)
            if cached is not None:
                return cached
        self._wait()
        request = urllib.request.Request(
            url, headers={"User-Agent": self.user_agent, "Accept-Language": "ja"}
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                body = response.read().decode(charset, errors="replace")
        finally:
            self._last_request = time.monotonic()
            self.requests_made += 1
        if self.cache is not None:
            self.cache.put(key, body)
        return body
