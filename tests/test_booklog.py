import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dokusho_import import booklog


class TestColumns(unittest.TestCase):
    def test_columns_match_official_spec_line_exactly(self):
        # 公式ヘルプが示す形式の原文と、列定義が文字単位で一致すること
        self.assertEqual(",".join(booklog.COLUMNS), booklog.SPEC_LINE)

    def test_spec_line_has_no_stray_spaces(self):
        self.assertEqual(booklog.SPEC_LINE, booklog.SPEC_LINE.replace(" ", ""))

    def test_column_order_and_count(self):
        self.assertEqual(len(booklog.COLUMNS), 11)
        self.assertEqual(booklog.COLUMNS[0], "サービスID")
        self.assertEqual(booklog.COLUMNS[1], "アイテムID")
        self.assertEqual(booklog.COLUMNS[2], "13桁ISBN")
        self.assertEqual(booklog.COLUMNS[-2], "登録日時")
        self.assertEqual(booklog.COLUMNS[-1], "読了日")

    def test_row_values_align_with_columns(self):
        self.assertEqual(len(booklog.Row().values()), len(booklog.COLUMNS))


class TestQuoting(unittest.TestCase):
    def test_plain_value_is_not_quoted(self):
        self.assertEqual(booklog.quote_field("9784297103262"), "9784297103262")

    def test_comma_is_quoted(self):
        self.assertEqual(booklog.quote_field("夏目, 漱石"), '"夏目, 漱石"')

    def test_inner_double_quote_is_doubled(self):
        self.assertEqual(booklog.quote_field('彼は "そう" 言った'), '"彼は ""そう"" 言った"')

    def test_newline_is_quoted(self):
        self.assertEqual(booklog.quote_field("一行目\n二行目"), '"一行目\n二行目"')

    def test_surrounding_space_is_quoted_so_it_survives(self):
        # 前後の空白が削られると値が変わるため引用する
        self.assertEqual(booklog.quote_field(" 4297103265 "), '" 4297103265 "')

    def test_inner_space_needs_no_quote(self):
        self.assertEqual(booklog.quote_field("夏目 漱石"), "夏目 漱石")

    def test_quote_all_quotes_nonempty_only(self):
        self.assertEqual(booklog.quote_field("abc", quote_all=True), '"abc"')
        self.assertEqual(booklog.quote_field("", quote_all=True), "")


class TestRow(unittest.TestCase):
    def test_format_row_has_ten_separators(self):
        line = booklog.format_row(booklog.Row(isbn13="9784297103262"))
        self.assertEqual(line.count(","), len(booklog.COLUMNS) - 1)

    def test_row_with_comma_in_review_keeps_column_count(self):
        import csv, io

        row = booklog.Row(isbn13="9784297103262", review="面白い, が長い", tags="小説,SF")
        parsed = next(csv.reader(io.StringIO(booklog.format_row(row))))
        self.assertEqual(len(parsed), len(booklog.COLUMNS))
        self.assertEqual(parsed[6], "面白い, が長い")
        self.assertEqual(parsed[7], "小説,SF")

    def test_validate_requires_item_id_or_isbn(self):
        self.assertTrue(booklog.Row().validate())
        self.assertFalse(booklog.Row(isbn13="9784297103262").validate())
        self.assertFalse(booklog.Row(item_id="4297103265").validate())

    def test_validate_rejects_short_registered_at(self):
        row = booklog.Row(isbn13="9784297103262", registered_at="2024-01-15")
        self.assertTrue(any("登録日時" in p for p in row.validate()))

    def test_registered_at_format(self):
        self.assertEqual(
            booklog.registered_at_from_date("2024-01-15"), "2024-01-15 00:00:00"
        )
        self.assertEqual(len(booklog.registered_at_from_date("2024-01-15")), 19)
        self.assertEqual(booklog.registered_at_from_date(""), "")


class TestWriteCsv(unittest.TestCase):
    def test_crlf_and_no_header_by_default(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.csv"
            booklog.write_csv([booklog.Row(isbn13="9784297103262")], path)
            raw = path.read_bytes()
            self.assertTrue(raw.endswith(b"\r\n"))
            self.assertNotIn("サービスID".encode(), raw)

    def test_header_option(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.csv"
            booklog.write_csv([], path, header=True)
            self.assertIn("サービスID", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
