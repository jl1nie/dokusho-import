"""ISBN / ASIN の判定と変換。

読書メーターの本ページに貼られている Amazon リンクの10文字は、
ISBN-10 の場合と Kindle 版の ASIN（B0... 始まり）の場合がある。
チェックディジットを必ず検証して、「たまたま10文字拾った」を落とす。
"""

from __future__ import annotations

import re

ISBN10_RE = re.compile(r"^[0-9]{9}[0-9Xx]$")
ISBN13_RE = re.compile(r"^97[89][0-9]{10}$")
ASIN_RE = re.compile(r"^B[0-9A-Z]{9}$")

_STRIP = re.compile(r"[^0-9A-Za-z]")


def normalize(code: str | None) -> str:
    """ハイフンや空白を落として大文字に寄せる。"""
    if not code:
        return ""
    return _STRIP.sub("", code).upper()


def is_valid_isbn10(code: str) -> bool:
    code = normalize(code)
    if not ISBN10_RE.match(code):
        return False
    total = sum(
        (10 - i) * (10 if ch == "X" else int(ch)) for i, ch in enumerate(code)
    )
    return total % 11 == 0


def is_valid_isbn13(code: str) -> bool:
    code = normalize(code)
    if not ISBN13_RE.match(code):
        return False
    total = sum((3 if i % 2 else 1) * int(ch) for i, ch in enumerate(code))
    return total % 10 == 0


def isbn10_to_13(code: str) -> str:
    """ISBN-10 を ISBN-13 に変換する。チェックディジットは再計算する。"""
    code = normalize(code)
    if not is_valid_isbn10(code):
        raise ValueError(f"ISBN-10 として不正: {code!r}")
    core = "978" + code[:9]
    check = (10 - sum((3 if i % 2 else 1) * int(ch) for i, ch in enumerate(core)) % 10) % 10
    return core + str(check)


def is_asin(code: str) -> bool:
    """Kindle 版などの ASIN か（= ISBN ではない）。"""
    return bool(ASIN_RE.match(normalize(code)))


def classify(code: str | None) -> tuple[str, str]:
    """Amazon の10文字コードを (種別, ISBN-13) に分類する。

    種別は "isbn10" / "isbn13" / "asin" / "unknown"。
    ISBN でない場合の ISBN-13 は空文字列。
    """
    code = normalize(code)
    if is_valid_isbn10(code):
        return "isbn10", isbn10_to_13(code)
    if is_valid_isbn13(code):
        return "isbn13", code
    if is_asin(code):
        return "asin", ""
    return "unknown", ""
