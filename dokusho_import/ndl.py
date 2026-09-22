"""ISBNが取れなかった本の逆引き（国立国会図書館サーチ OpenSearch API）。

Kindle版しか登録がない本などが対象。複数の版が返る場合は
出版日の新しいものを採る（= 最新版）。
openBD は ISBN から引く専用で逆引きできないため使わない。
"""

from __future__ import annotations

import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from . import isbn as isbn_mod
from .textnorm import clean, collapse_for_match

ENDPOINT = "https://ndlsearch.ndl.go.jp/api/opensearch"

_NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "dcndl": "http://ndl.go.jp/dcndl/terms/",
}


@dataclass
class Candidate:
    isbn13: str
    title: str
    author: str
    issued: str  # "YYYY" / "YYYY-MM" / "YYYY-MM-DD"、不明なら空


def build_url(title: str, author: str = "", count: int = 20) -> str:
    params = {"title": clean(title), "cnt": str(count)}
    if clean(author):
        params["creator"] = clean(author)
    return ENDPOINT + "?" + urllib.parse.urlencode(params)


def parse_candidates(xml_text: str) -> list[Candidate]:
    root = ET.fromstring(xml_text)
    out: list[Candidate] = []
    for item in root.iter("item"):
        isbn13 = ""
        for ident in item.findall("dc:identifier", _NS):
            code = isbn_mod.normalize(ident.text or "")
            kind, converted = isbn_mod.classify(code)
            if kind in ("isbn10", "isbn13"):
                isbn13 = converted
                break
        if not isbn13:
            continue
        issued = ""
        for tag in ("dcterms:issued", "dc:date"):
            node = item.find(tag, _NS)
            if node is not None and node.text:
                issued = clean(node.text)
                break
        title_node = item.find("dc:title", _NS)
        creator_node = item.find("dc:creator", _NS)
        out.append(
            Candidate(
                isbn13=isbn13,
                title=clean(title_node.text if title_node is not None else ""),
                author=clean(creator_node.text if creator_node is not None else ""),
                issued=issued,
            )
        )
    return out


def _issued_key(value: str) -> tuple[int, int, int]:
    """出版日を比較可能なキーにする。不明な部分は0扱いで後ろに回す。"""
    digits = [int(p) for p in value.replace(".", "-").replace("/", "-").split("-") if p.isdigit()]
    digits += [0, 0, 0]
    return (digits[0], digits[1], digits[2])


def pick_latest(candidates: list[Candidate], title: str) -> Candidate | None:
    """タイトルが一致する候補のうち、出版日が最新のものを返す。

    タイトル一致は空白を除去した部分一致で見る（読書メーター側の表記に
    副題やシリーズ名が付くことがあるため）。
    """
    key = collapse_for_match(title)
    matched = [
        c
        for c in candidates
        if key and (key in collapse_for_match(c.title) or collapse_for_match(c.title) in key)
    ]
    pool = matched or candidates
    if not pool:
        return None
    return max(pool, key=lambda c: _issued_key(c.issued))
