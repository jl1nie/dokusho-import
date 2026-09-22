"""文字列の正規化。

ブクログのCSVに入る値（タイトル・著者名・レビュー）や、読書メーターの
HTMLから抜いた値には、半角/全角スペース・NBSP・改行が混ざる。
突き合わせにも出力にも効くので、入口で一度だけ潰しておく。
"""

from __future__ import annotations

import re
import unicodedata
from html import unescape

# 半角/全角スペース、タブ、改行、NBSP、ゼロ幅スペースをまとめて空白扱いにする
_WHITESPACE = re.compile(r"[\s   -​  　﻿]+")
# CSVを壊す制御文字（改行はすでに空白化済み）
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean(value: str | None) -> str:
    """HTMLエンティティを戻し、空白を単一スペースに畳んで前後を落とす。"""
    if not value:
        return ""
    text = unescape(value)
    text = _CONTROL.sub("", text)
    return _WHITESPACE.sub(" ", text).strip()


def collapse_for_match(value: str | None) -> str:
    """検索キー用。空白を完全に除去し、全角英数を半角に寄せる。

    「夏目 漱石」「夏目　漱石」「夏目漱石」を同じキーにするため。
    出力には使わない（表示は clean() の結果を使う）。
    """
    text = clean(value)
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    return _WHITESPACE.sub("", text)
