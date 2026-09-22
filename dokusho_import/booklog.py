"""ブクログのインポートCSVを書き出す。

列仕様は公式ヘルプ「他の読書管理サイトからブクログへデータを移行したい」の
記載どおり（SPEC_LINE に原文を置き、COLUMNS との一致をテストで固定している）:

    サービスID,アイテムID,13桁ISBN,カテゴリ,評価,読書状況,レビュー,タグ,非公開メモ,登録日時,読了日

確定している制約:
  - 「アイテムID」「13桁ISBN」はどちらか必須。アイテムIDが不明なら
    3列目の13桁ISBNを入れる
  - 登録日時は "yyyy-mm-dd hh:mm:ss"。これを守らないと全件が
    インポート日時に上書きされる
  - サービスID: Amazon.co.jp=1, Amazon.com=2, iTunes=4

UNCONFIRMED にまとめた項目だけがまだ未確定。ここを差し替えれば済むように
1か所に隔離してある。

アップロード手順: 画面右上の本棚マーク > 本棚の灰色部分のスパナマーク >
インポート > 「CSV登録」からファイルをアップロード。
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path

from .textnorm import clean

# 公式ヘルプが示すCSV形式の原文。COLUMNS と一致することをテストで固定する。
SPEC_LINE = (
    "サービスID,アイテムID,13桁ISBN,カテゴリ,評価,読書状況,"
    "レビュー,タグ,非公開メモ,登録日時,読了日"
)

COLUMNS = [
    "サービスID",
    "アイテムID",
    "13桁ISBN",
    "カテゴリ",
    "評価",
    "読書状況",
    "レビュー",
    "タグ",
    "非公開メモ",
    "登録日時",
    "読了日",
]

SERVICE_AMAZON_CO_JP = "1"

# 読書状況。ブクログUI上の5段階に対応する文字列。
STATUS_UNSET = "未設定"
STATUS_WANT = "読みたい"
STATUS_READING = "いま読んでる"
STATUS_READ = "読み終わった"
STATUS_STOCK = "積読"

UNCONFIRMED = """\
列の並びと必須条件は公式ヘルプで確定済み。以下はまだ未確定:
  1. 読書状況をCSVでは日本語文字列で書くのか数値コードなのか
     （本実装は日本語文字列。--status で差し替え可能）
  2. ヘッダ行が必要か（本実装は既定でヘッダなし。--header で付与）
  3. 文字コード（本実装は既定 UTF-8。--encoding で変更可能）
--limit 1 で1件だけインポートして上の3点を確定させてから全件を流すこと。
"""

# CSVを壊す、またはパーサ側で前後が削られうる文字
_MUST_QUOTE = set(',"\r\n')


@dataclass
class Row:
    """ブクログCSVの1行。全カラムを明示的に持つ。"""

    item_id: str = ""       # ISBN-10 または ASIN
    isbn13: str = ""
    service_id: str = ""
    category: str = ""
    rating: str = ""        # 0-5。読書メーターに相当項目がないので既定は空
    status: str = STATUS_READ
    review: str = ""
    tags: str = ""
    private_memo: str = ""
    registered_at: str = ""  # "yyyy-mm-dd hh:mm:ss"
    read_date: str = ""      # "yyyy-mm-dd"

    def values(self) -> list[str]:
        return [
            self.service_id,
            self.item_id,
            self.isbn13,
            self.category,
            self.rating,
            self.status,
            self.review,
            self.tags,
            self.private_memo,
            self.registered_at,
            self.read_date,
        ]

    def validate(self) -> list[str]:
        """行として成立しない点を挙げる。空リストなら問題なし。"""
        problems: list[str] = []
        if not self.item_id and not self.isbn13:
            problems.append("アイテムIDと13桁ISBNの両方が空（どちらか必須）")
        if self.registered_at and len(self.registered_at) != 19:
            problems.append(
                f"登録日時が yyyy-mm-dd hh:mm:ss 形式でない: {self.registered_at!r}"
            )
        if self.read_date and len(self.read_date) != 10:
            problems.append(f"読了日が yyyy-mm-dd 形式でない: {self.read_date!r}")
        return problems


def registered_at_from_date(read_date: str, time_of_day: str = "00:00:00") -> str:
    """読了日 "yyyy-mm-dd" から登録日時 "yyyy-mm-dd hh:mm:ss" を作る。"""
    date = clean(read_date)
    if not date:
        return ""
    return f"{date} {time_of_day}"


def quote_field(value: str, quote_all: bool = False) -> str:
    """1カラムをCSVの1フィールドに整形する。

    カンマ・引用符・改行に加えて、前後に空白が残っている場合も引用する。
    ブクログ側のパーサが引用なしフィールドの前後空白を削っても値が
    変わらないようにするため。
    """
    text = "" if value is None else str(value)
    needs = quote_all and text != ""
    needs = needs or any(ch in _MUST_QUOTE for ch in text)
    needs = needs or (text != text.strip())
    if needs:
        return '"' + text.replace('"', '""') + '"'
    return text


def format_row(row: Row, quote_all: bool = False) -> str:
    return ",".join(quote_field(v, quote_all) for v in row.values())


def write_csv(
    rows: list[Row],
    path: Path,
    *,
    encoding: str = "utf-8",
    newline: str = "\r\n",
    header: bool = False,
    quote_all: bool = False,
) -> None:
    lines: list[str] = []
    if header:
        lines.append(",".join(quote_field(c, quote_all) for c in COLUMNS))
    lines.extend(format_row(r, quote_all) for r in rows)
    text = newline.join(lines) + (newline if lines else "")
    path.write_text(text, encoding=encoding, newline="")


def write_unresolved_csv(records, path: Path, *, encoding: str = "utf-8") -> None:
    """ISBNが取れなかった本を、手作業で埋められる形で出す。"""
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(
        ["book_id", "読書メーターURL", "タイトル", "著者", "読了日", "Amazonコード", "理由"]
    )
    for r in records:
        writer.writerow(
            [
                r.book_id,
                r.url,
                r.title,
                r.author,
                r.read_date,
                r.amazon_code,
                " / ".join(r.notes),
            ]
        )
    path.write_text(buf.getvalue(), encoding=encoding, newline="")
