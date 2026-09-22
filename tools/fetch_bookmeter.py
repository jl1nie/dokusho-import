#!/usr/bin/env python3
"""読書メーターのページを取得してZIPにまとめるだけのスクリプト。

解析は一切しない。あとから何度でもやり直せるように、生HTMLをそのまま残す。
標準ライブラリだけで動くので、このファイル1つをコピーすれば使える。

    python3 fetch_bookmeter.py 621778

途中で止まっても、同じコマンドをもう一度実行すれば続きから再開する
（取得済みのファイルは読み直さない）。

できあがった bookmeter_621778.zip を解凍すれば、そのまま

    python3 -m dokusho_import.cli --html-dir <解凍先> --out booklog.csv

に渡せる。
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_BASE = "https://bookmeter.com"
BOOK_LINK = re.compile(r'href="(?:https://bookmeter\.com)?/books/(\d+)"')

# 連絡先を自分のものに書き換えて使うことを想定している
USER_AGENT = "dokusho-import/0.1 (personal bookshelf export; contact: set-your-email-here)"


class Fetcher:
    def __init__(self, interval: float, user_agent: str, timeout: float = 30.0):
        self.interval = interval
        self.user_agent = user_agent
        self.timeout = timeout
        self.last = 0.0
        self.count = 0

    def get(self, url: str) -> str:
        if self.last:
            wait = self.interval - (time.monotonic() - self.last)
            if wait > 0:
                time.sleep(wait + random.uniform(0, 0.5))
        request = urllib.request.Request(
            url, headers={"User-Agent": self.user_agent, "Accept-Language": "ja"}
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        finally:
            self.last = time.monotonic()
            self.count += 1


def save(directory: Path, name: str, text: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(text, encoding="utf-8")


def fetch_or_reuse(fetcher: Fetcher, directory: Path, name: str, url: str, log) -> str:
    """すでに取得済みならファイルから読む。なければ取得して保存する。"""
    path = directory / name
    if path.exists() and path.stat().st_size > 0:
        log(f"  skip {name}（取得済み）")
        return path.read_text(encoding="utf-8", errors="replace")
    text = fetcher.get(url)
    save(directory, name, text)
    log(f"  got  {name} ({len(text):,} bytes)")
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="読書メーターのHTMLを取得してZIPにする")
    parser.add_argument("user_id", help="読書メーターのユーザーID（例: 621778）")
    parser.add_argument("--out", type=Path, help="出力ZIP（既定: bookmeter_<id>.zip）")
    parser.add_argument("--workdir", type=Path, help="作業ディレクトリ（既定: bookmeter_<id>）")
    parser.add_argument("--interval", type=float, default=2.0, help="リクエスト間隔（秒）")
    parser.add_argument("--max-pages", type=int, default=200)
    parser.add_argument("--limit", type=int, help="先頭N冊だけ取得（お試し用）")
    parser.add_argument("--user-agent", default=USER_AGENT)
    parser.add_argument("--base", default=DEFAULT_BASE, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    workdir = args.workdir or Path(f"bookmeter_{args.user_id}")
    out = args.out or Path(f"bookmeter_{args.user_id}.zip")
    fetcher = Fetcher(args.interval, args.user_agent)

    def log(message: str) -> None:
        print(message, file=sys.stderr, flush=True)

    log(f"作業ディレクトリ: {workdir}")
    try:
        log("プロフィールを取得中...")
        fetch_or_reuse(
            fetcher, workdir, "user.html", f"{args.base}/users/{args.user_id}", log
        )

        log("読了本の一覧を取得中...")
        book_ids: list[str] = []
        seen: set[str] = set()
        for page in range(1, args.max_pages + 1):
            html = fetch_or_reuse(
                fetcher,
                workdir,
                f"read_page_{page}.html",
                f"{args.base}/users/{args.user_id}/books/read?page={page}",
                log,
            )
            # 1冊につき表紙とタイトルで2本リンクが出るので、ページ内でも重複を除く
            fresh = []
            for book_id in BOOK_LINK.findall(html):
                if book_id not in seen:
                    seen.add(book_id)
                    fresh.append(book_id)
            if not fresh:
                log(f"  page {page} に新しい本がないので終了")
                break
            book_ids.extend(fresh)
            log(f"  page {page}: 新規 {len(fresh)} 冊 / 累計 {len(book_ids)} 冊")

        if args.limit:
            book_ids = book_ids[: args.limit]

        log(f"本ページを取得中（{len(book_ids)} 冊）...")
        for i, book_id in enumerate(book_ids, 1):
            log(f"[{i}/{len(book_ids)}]")
            fetch_or_reuse(
                fetcher, workdir, f"book_{book_id}.html", f"{args.base}/books/{book_id}", log
            )
    except KeyboardInterrupt:
        log("\n中断した。同じコマンドをもう一度実行すれば続きから再開する。")
        return 130
    except urllib.error.URLError as exc:
        log(f"\n取得に失敗: {exc}")
        log("同じコマンドをもう一度実行すれば、取得済み分は飛ばして続きから再開する。")
        return 1

    manifest = {
        "user_id": args.user_id,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "base": args.base,
        "book_count": len(book_ids),
        "requests_made": fetcher.count,
        "files": sorted(p.name for p in workdir.glob("*.html")),
    }
    save(workdir, "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    files = sorted(workdir.iterdir())
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.name)

    log("")
    log(f"ZIPを作成: {out} （{out.stat().st_size:,} bytes / {len(files)} ファイル）")
    log(f"リクエスト回数: {fetcher.count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
