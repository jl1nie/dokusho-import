"""読書メーターのユーザーID → ブクログインポートCSV。

    python3 -m dokusho_import.cli --user-id 123456 --out booklog.csv

ネットワークに出ずに手元のHTMLだけで確かめたい場合:

    python3 -m dokusho_import.cli --html-dir ./fixtures --out booklog.csv

--html-dir は read_page_1.html, read_page_2.html, ... と
book_<book_id>.html を読む（ブラウザの「ページを保存」でそのまま使える）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import bookmeter, booklog, ndl
from .fetcher import DEFAULT_USER_AGENT, Cache, Fetcher
from .isbn import is_valid_isbn13


class LocalSource:
    """保存済みHTMLを読むだけの取得元。ネットワークに出ない。"""

    def __init__(self, directory: Path):
        self.directory = directory
        self.requests_made = 0

    def read_list(self, page: int) -> str | None:
        path = self.directory / f"read_page_{page}.html"
        return path.read_text(encoding="utf-8", errors="replace") if path.exists() else None

    def book(self, book_id: str) -> str | None:
        path = self.directory / f"book_{book_id}.html"
        return path.read_text(encoding="utf-8", errors="replace") if path.exists() else None

    def user_page(self) -> str | None:
        path = self.directory / "user.html"
        return path.read_text(encoding="utf-8", errors="replace") if path.exists() else None


class RemoteSource:
    """読書メーターから取得する。

    save_dir を渡すと、取得した生HTMLを LocalSource が読める名前で
    そのまま書き出す。一度オンラインで流しておけば、以後は
    --html-dir で同じデータをネットワークなしに再現できる。
    """

    def __init__(self, user_id: str, fetcher: Fetcher, save_dir: Path | None = None):
        self.user_id = user_id
        self.fetcher = fetcher
        self.save_dir = save_dir
        if save_dir is not None:
            save_dir.mkdir(parents=True, exist_ok=True)

    @property
    def requests_made(self) -> int:
        return self.fetcher.requests_made

    def _save(self, name: str, html: str | None) -> str | None:
        if html is not None and self.save_dir is not None:
            (self.save_dir / name).write_text(html, encoding="utf-8")
        return html

    def read_list(self, page: int) -> str | None:
        # 一覧はキャッシュしない（読了本が増えると内容が変わる）
        html = self.fetcher.get(bookmeter.read_list_url(self.user_id, page), cache_key=None)
        return self._save(f"read_page_{page}.html", html)

    def book(self, book_id: str) -> str | None:
        url = bookmeter.BOOK_PAGE.format(book_id=book_id)
        html = self.fetcher.get(url, cache_key=f"book:{book_id}")
        return self._save(f"book_{book_id}.html", html)

    def user_page(self) -> str | None:
        html = self.fetcher.get(
            bookmeter.USER_PAGE.format(user_id=self.user_id), cache_key=None
        )
        return self._save("user.html", html)


def collect_entries(source, max_pages: int, log) -> list[bookmeter.ListEntry]:
    entries: list[bookmeter.ListEntry] = []
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        html = source.read_list(page)
        if html is None:
            break
        found = bookmeter.parse_read_list(html)
        fresh = [e for e in found if e.book_id not in seen]
        log(f"  page {page}: {len(found)} 件（新規 {len(fresh)} 件）")
        if not fresh:
            break
        for entry in fresh:
            seen.add(entry.book_id)
            entries.append(entry)
    return entries


def resolve_books(source, entries, log) -> list[bookmeter.BookRecord]:
    records: list[bookmeter.BookRecord] = []
    for i, entry in enumerate(entries, 1):
        html = source.book(entry.book_id)
        if html is None:
            record = bookmeter.BookRecord(book_id=entry.book_id, code_kind="none")
            record.notes.append("本ページのHTMLが手元にない")
        else:
            record = bookmeter.parse_book_page(entry.book_id, html)
        record.read_date = entry.read_date
        records.append(record)
        mark = record.isbn13 or f"[{record.code_kind}]"
        log(f"  [{i}/{len(entries)}] {entry.book_id} {mark} {record.title[:32]}")
    return records


def apply_ndl_fallback(records, fetcher: Fetcher, log) -> None:
    """ISBNが取れなかった本をタイトル・著者で逆引きし、最新版を採る。"""
    targets = [r for r in records if not r.resolved and r.title]
    for record in targets:
        url = ndl.build_url(record.title, record.author)
        try:
            xml_text = fetcher.get(url, cache_key=f"ndl:{record.title}|{record.author}")
            candidate = ndl.pick_latest(ndl.parse_candidates(xml_text), record.title)
        except Exception as exc:  # 逆引き失敗は未解決として残すだけ
            record.notes.append(f"NDL逆引き失敗: {exc}")
            continue
        if candidate is None:
            record.notes.append("NDLに該当なし")
            continue
        record.isbn13 = candidate.isbn13
        record.code_kind = "ndl_latest"
        record.notes.append(
            f"NDL逆引きで最新版を採用（{candidate.issued or '出版日不明'} / {candidate.title}）"
        )
        log(f"  NDL: {record.title[:28]} -> {candidate.isbn13} ({candidate.issued})")


def build_rows(records, args) -> list[booklog.Row]:
    rows: list[booklog.Row] = []
    for record in records:
        if not record.isbn13:
            continue
        item_id = record.amazon_code if record.code_kind in ("isbn10", "isbn13") else ""
        memo = record.url if args.memo_source else ""
        if memo and record.code_kind == "ndl_latest":
            memo += " (ISBN: NDL逆引き/最新版)"
        rows.append(
            booklog.Row(
                service_id=booklog.SERVICE_AMAZON_CO_JP if item_id else "",
                item_id=item_id,
                isbn13=record.isbn13,
                status=args.status,
                tags=args.tags,
                private_memo=memo,
                registered_at=(
                    booklog.registered_at_from_date(record.read_date)
                    if args.registered_from_read_date
                    else ""
                ),
                read_date=record.read_date,
            )
        )
    return rows


def audit(entries, records, rows, expected: int | None, log) -> list[str]:
    """出力の妥当性を機械的に確かめる。問題を文字列で返す。"""
    problems: list[str] = []

    if expected is not None and expected != len(entries):
        problems.append(
            f"冊数不一致: プロフィール {expected} 冊 / 取得 {len(entries)} 冊。"
            "ページングの取りこぼしの可能性がある。"
        )

    for row in rows:
        for problem in row.validate():
            problems.append(f"{row.isbn13 or row.item_id}: {problem}")
        if row.isbn13 and not is_valid_isbn13(row.isbn13):
            problems.append(f"{row.isbn13}: ISBN-13のチェックディジットが不正")

    counts: dict[str, list[str]] = {}
    for record in records:
        if record.isbn13:
            counts.setdefault(record.isbn13, []).append(record.book_id)
    for isbn13, book_ids in counts.items():
        if len(book_ids) > 1:
            problems.append(
                f"{isbn13}: 複数のbook_idが同じISBNに解決した（{', '.join(book_ids)}）"
            )

    log("")
    log(f"一覧から取得した本: {len(entries)} 冊")
    log(f"ISBN解決済み: {len(rows)} 冊")
    log(f"未解決: {len([r for r in records if not r.resolved])} 冊")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="読書メーター → ブクログCSV")
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--user-id", help="読書メーターのユーザーID")
    source_group.add_argument("--html-dir", type=Path, help="保存済みHTMLのディレクトリ")
    parser.add_argument("--out", type=Path, default=Path("booklog.csv"))
    parser.add_argument("--unresolved-out", type=Path, default=Path("unresolved.csv"))
    parser.add_argument("--cache", type=Path, default=Path(".cache/bookmeter.json"))
    parser.add_argument("--max-pages", type=int, default=200)
    parser.add_argument("--interval", type=float, default=2.0, help="リクエスト間隔（秒）")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--expect", type=int, help="期待する冊数。合わなければ失敗扱い")
    parser.add_argument("--status", default=booklog.STATUS_READ)
    parser.add_argument("--tags", default="")
    parser.add_argument("--encoding", default="utf-8", help="utf-8 / utf-8-sig / cp932")
    parser.add_argument("--header", action="store_true", help="ヘッダ行を付ける")
    parser.add_argument("--quote-all", action="store_true", help="全カラムを引用符で囲む")
    parser.add_argument("--lf", action="store_true", help="改行をLFにする（既定はCRLF）")
    parser.add_argument("--no-memo-source", dest="memo_source", action="store_false")
    parser.add_argument(
        "--no-registered-from-read-date",
        dest="registered_from_read_date",
        action="store_false",
    )
    parser.add_argument("--ndl-fallback", action="store_true", help="未解決分をNDLで逆引き")
    parser.add_argument("--limit", type=int, help="先頭N冊だけ処理（動作確認用）")
    parser.add_argument(
        "--save-html",
        type=Path,
        help="取得した生HTMLをこのディレクトリに保存する（後で --html-dir に渡せる）",
    )
    args = parser.parse_args(argv)

    def log(message: str) -> None:
        print(message, file=sys.stderr)

    fetcher = Fetcher(
        cache=Cache(args.cache),
        min_interval=args.interval,
        user_agent=args.user_agent,
    )
    if args.html_dir:
        source = LocalSource(args.html_dir)
    else:
        source = RemoteSource(args.user_id, fetcher, save_dir=args.save_html)
        if args.save_html:
            log(f"生HTMLを {args.save_html} に保存する")

    log("読了本の一覧を取得中...")
    entries = collect_entries(source, args.max_pages, log)
    if not entries:
        log("本が1冊も取れなかった。URLの形かHTML構造の変更を疑う。")
        return 1

    expected = args.expect
    if expected is None:
        user_html = source.user_page()
        if user_html:
            expected = bookmeter.parse_read_count(user_html)
            if expected is not None:
                log(f"プロフィールの読んだ本: {expected} 冊")

    if args.limit:
        entries = entries[: args.limit]
        expected = None

    log("各本のページからISBNを取得中...")
    records = resolve_books(source, entries, log)

    if args.ndl_fallback and not args.html_dir:
        log("未解決分をNDLで逆引き中...")
        apply_ndl_fallback(records, fetcher, log)

    rows = build_rows(records, args)
    booklog.write_csv(
        rows,
        args.out,
        encoding=args.encoding,
        newline="\n" if args.lf else "\r\n",
        header=args.header,
        quote_all=args.quote_all,
    )
    unresolved = [r for r in records if not r.resolved]
    booklog.write_unresolved_csv(unresolved, args.unresolved_out, encoding=args.encoding)

    problems = audit(entries, records, rows, expected, log)
    log(f"書き出し: {args.out} / 未解決: {args.unresolved_out}")
    log("")
    log(booklog.UNCONFIRMED)

    if problems:
        log("検証で問題が見つかった:")
        for problem in problems:
            log(f"  - {problem}")
        return 2
    log("検証OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
