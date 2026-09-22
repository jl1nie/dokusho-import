"""読書メーターのHTMLから book_id / ISBN / 書誌を取り出す。

方針:
  - CSSクラス名に依存しない。読書メーターの内部クラス名は変わりうるので、
    「/books/数字 へのリンク」「amazon.co.jp/dp/10文字」という、意味が
    変わらない構造だけを手がかりにする。
  - 見つからなかったものは黙って飛ばさず、理由付きで未解決として返す。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import isbn as isbn_mod
from .textnorm import clean

BASE = "https://bookmeter.com"

# 「読んだ本」一覧。page は1始まり。
READ_LIST = BASE + "/users/{user_id}/books/read?page={page}"
USER_PAGE = BASE + "/users/{user_id}"
BOOK_PAGE = BASE + "/books/{book_id}"

_BOOK_LINK = re.compile(r'href="(?:https://bookmeter\.com)?/books/(\d+)"')
# /dp/ 以外の旧形式リンクも拾う
_AMAZON_CODE = re.compile(
    r"amazon\.(?:co\.jp|com)/"
    r"(?:[^\"'?]*?/)?"
    r"(?:dp|gp/product|exec/obidos/ASIN)/"
    r"([0-9A-Za-z]{10})"
)
_DATE = re.compile(r"(\d{4})[/\-年](\d{1,2})[/\-月](\d{1,2})")
_OG_TITLE = re.compile(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"')
_OG_TITLE_ALT = re.compile(r'<meta[^>]+content="([^"]*)"[^>]+property="og:title"')
_H1 = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S)
_AUTHOR_LINK = re.compile(r'href="(?:https://bookmeter\.com)?/authors/\d+"[^>]*>(.*?)</a>', re.S)
_TAGS = re.compile(r"<[^>]+>")
# 「読んだ本 123冊」のような表記から総数を取る
_READ_COUNT = re.compile(r"読んだ本[^0-9]{0,40}?([0-9,]+)")


@dataclass
class ListEntry:
    """一覧ページの1件。"""

    book_id: str
    read_date: str = ""  # "YYYY-MM-DD"、取れなければ空


@dataclass
class BookRecord:
    """本ページから取れた情報。"""

    book_id: str
    title: str = ""
    author: str = ""
    amazon_code: str = ""
    code_kind: str = ""  # isbn10 / isbn13 / asin / unknown / none
    isbn13: str = ""
    read_date: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        return BOOK_PAGE.format(book_id=self.book_id)

    @property
    def resolved(self) -> bool:
        return bool(self.isbn13)


def read_list_url(user_id: str, page: int) -> str:
    return READ_LIST.format(user_id=user_id, page=page)


def _strip_tags(html: str) -> str:
    return clean(_TAGS.sub(" ", html))


def _iso_date(html_chunk: str) -> str:
    m = _DATE.search(html_chunk)
    if not m:
        return ""
    year, month, day = (int(g) for g in m.groups())
    if not (1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31):
        return ""
    return f"{year:04d}-{month:02d}-{day:02d}"


def parse_read_list(html: str) -> list[ListEntry]:
    """一覧ページから book_id と読了日を、出現順・重複なしで取り出す。

    読了日は「その本のリンクから次の本のリンクまで」の範囲にある最初の
    日付を採る。日付が本ごとのブロックの中にある構造に依存するだけで、
    クラス名には依存しない。
    """
    matches = list(_BOOK_LINK.finditer(html))
    entries: list[ListEntry] = []
    seen: set[str] = set()
    for i, m in enumerate(matches):
        book_id = m.group(1)
        end = matches[i + 1].start() if i + 1 < len(matches) else len(html)
        chunk = html[m.end() : end]
        if book_id in seen:
            # 同じ本への2本目のリンク（表紙とタイトル等）。日付だけ補う。
            if not entries[[e.book_id for e in entries].index(book_id)].read_date:
                date = _iso_date(chunk)
                if date:
                    entries[[e.book_id for e in entries].index(book_id)].read_date = date
            continue
        seen.add(book_id)
        entries.append(ListEntry(book_id=book_id, read_date=_iso_date(chunk)))
    return entries


def parse_read_count(html: str) -> int | None:
    """ユーザーページの「読んだ本 N冊」から総数を取る。取れなければ None。"""
    m = _READ_COUNT.search(_strip_tags(html))
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return None


def parse_book_page(book_id: str, html: str) -> BookRecord:
    """本ページから Amazon コード・タイトル・著者を取り出す。"""
    record = BookRecord(book_id=book_id)

    title = ""
    for pattern in (_OG_TITLE, _OG_TITLE_ALT):
        m = pattern.search(html)
        if m:
            title = clean(m.group(1))
            break
    if not title:
        m = _H1.search(html)
        if m:
            title = _strip_tags(m.group(1))
    # og:title には「 - 読書メーター」のようなサフィックスが付く場合がある
    record.title = re.sub(r"\s*[|｜\-−–—]\s*読書メーター\s*$", "", title).strip()

    authors = [_strip_tags(a) for a in _AUTHOR_LINK.findall(html)]
    seen: set[str] = set()
    uniq = [a for a in authors if a and not (a in seen or seen.add(a))]
    record.author = ", ".join(uniq)

    codes = [isbn_mod.normalize(c) for c in _AMAZON_CODE.findall(html)]
    # ISBNとして妥当なものを優先する。同一ページに複数リンクがあっても、
    # 先に見つかった「妥当なISBN」を採る。
    for code in codes:
        kind, isbn13 = isbn_mod.classify(code)
        if kind in ("isbn10", "isbn13"):
            record.amazon_code = code
            record.code_kind = kind
            record.isbn13 = isbn13
            return record

    if codes:
        record.amazon_code = codes[0]
        record.code_kind, record.isbn13 = isbn_mod.classify(codes[0])
        if record.code_kind == "asin":
            record.notes.append("Kindle版などのASINのみ。ISBNなし。")
        else:
            record.notes.append(f"Amazonコードを解釈できない: {codes[0]}")
    else:
        record.code_kind = "none"
        record.notes.append("本ページにAmazonリンクが見つからない。")
    return record
