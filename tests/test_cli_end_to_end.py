"""合成フィクスチャを通した通しの検証（ネットワークに出ない）。"""

import contextlib
import csv
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dokusho_import import booklog
from dokusho_import.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


class TestEndToEnd(unittest.TestCase):
    def run_cli(self, *extra):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        out = root / "booklog.csv"
        unresolved = root / "unresolved.csv"
        argv = [
            "--html-dir", str(FIXTURES),
            "--out", str(out),
            "--unresolved-out", str(unresolved),
            "--cache", str(root / "cache.json"),
            *extra,
        ]
        with contextlib.redirect_stderr(io.StringIO()):
            code = main(argv)
        return code, out, unresolved

    def test_exit_code_zero_and_rows_written(self):
        code, out, unresolved = self.run_cli()
        self.assertEqual(code, 0)
        rows = list(csv.reader(io.StringIO(out.read_text(encoding="utf-8"))))
        # ISBNが取れた2冊だけがCSVに入る
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(len(row), len(booklog.COLUMNS))

    def test_isbn_and_item_id_columns(self):
        _, out, _ = self.run_cli()
        rows = list(csv.reader(io.StringIO(out.read_text(encoding="utf-8"))))
        by_isbn = {r[2]: r for r in rows}
        self.assertIn("9784297103262", by_isbn)
        row = by_isbn["9784297103262"]
        self.assertEqual(row[0], "1")            # サービスID = Amazon.co.jp
        self.assertEqual(row[1], "4297103265")   # アイテムID = ISBN-10
        self.assertEqual(row[5], "読み終わった")  # 読書状況
        self.assertEqual(row[9], "2024-01-15 00:00:00")  # 登録日時
        self.assertEqual(row[10], "2024-01-15")  # 読了日

    def test_unresolved_books_are_reported_not_dropped_silently(self):
        _, _, unresolved = self.run_cli()
        rows = list(csv.reader(io.StringIO(unresolved.read_text(encoding="utf-8"))))
        self.assertEqual(rows[0][0], "book_id")
        ids = {r[0] for r in rows[1:]}
        self.assertEqual(ids, {"33002", "44003"})  # ASINのみ / リンクなし

    def test_unresolved_rows_carry_url_and_reason(self):
        _, _, unresolved = self.run_cli()
        rows = list(csv.reader(io.StringIO(unresolved.read_text(encoding="utf-8"))))
        for row in rows[1:]:
            self.assertTrue(row[1].startswith("https://bookmeter.com/books/"))
            self.assertTrue(row[6])

    def test_count_mismatch_is_flagged(self):
        code, _, _ = self.run_cli("--expect", "140")
        self.assertEqual(code, 2)

    def test_expected_count_match_passes(self):
        code, _, _ = self.run_cli("--expect", "4")
        self.assertEqual(code, 0)

    def test_status_override(self):
        _, out, _ = self.run_cli("--status", booklog.STATUS_STOCK)
        rows = list(csv.reader(io.StringIO(out.read_text(encoding="utf-8"))))
        self.assertTrue(all(r[5] == "積読" for r in rows))

    def test_memo_carries_source_url(self):
        _, out, _ = self.run_cli()
        rows = list(csv.reader(io.StringIO(out.read_text(encoding="utf-8"))))
        self.assertTrue(all(r[8].startswith("https://bookmeter.com/books/") for r in rows))

    def test_header_option_adds_one_line(self):
        _, out, _ = self.run_cli("--header")
        rows = list(csv.reader(io.StringIO(out.read_text(encoding="utf-8"))))
        self.assertEqual(rows[0], booklog.COLUMNS)
        self.assertEqual(len(rows), 3)


if __name__ == "__main__":
    unittest.main()
