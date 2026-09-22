import unittest
from pathlib import Path

from dokusho_import import bookmeter

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class TestParseReadList(unittest.TestCase):
    def setUp(self):
        self.entries = bookmeter.parse_read_list(load("read_page_1.html"))

    def test_dedupes_multiple_links_to_same_book(self):
        # 表紙とタイトルで同じ本へのリンクが2本あっても1件にする
        self.assertEqual([e.book_id for e in self.entries],
                         ["13558368", "22001", "33002", "44003"])

    def test_extracts_read_date_as_iso(self):
        by_id = {e.book_id: e.read_date for e in self.entries}
        self.assertEqual(by_id["13558368"], "2024-01-15")
        self.assertEqual(by_id["22001"], "2024-02-03")  # 2024/2/3 の0埋め
        self.assertEqual(by_id["33002"], "2023-12-31")

    def test_missing_date_is_empty_not_guessed(self):
        by_id = {e.book_id: e.read_date for e in self.entries}
        self.assertEqual(by_id["44003"], "")

    def test_empty_page_yields_nothing(self):
        self.assertEqual(bookmeter.parse_read_list(load("read_page_2.html")), [])

    def test_date_does_not_leak_from_next_book(self):
        # 44003 は最後の本で日付がない。前の本の日付を拾っていないこと
        self.assertNotEqual(self.entries[-1].read_date, "2023-12-31")


class TestParseReadCount(unittest.TestCase):
    def test_reads_count_from_user_page(self):
        self.assertEqual(bookmeter.parse_read_count(load("user.html")), 4)

    def test_returns_none_when_absent(self):
        self.assertIsNone(bookmeter.parse_read_count("<html><body></body></html>"))


class TestParseBookPage(unittest.TestCase):
    def test_isbn10_from_dp_link(self):
        r = bookmeter.parse_book_page("13558368", load("book_13558368.html"))
        self.assertEqual(r.amazon_code, "4297103265")
        self.assertEqual(r.code_kind, "isbn10")
        self.assertEqual(r.isbn13, "9784297103262")
        self.assertTrue(r.resolved)

    def test_strips_bookmeter_suffix_from_title(self):
        r = bookmeter.parse_book_page("13558368", load("book_13558368.html"))
        self.assertEqual(r.title, "Go言語による並行処理")

    def test_normalizes_fullwidth_space_in_author(self):
        r = bookmeter.parse_book_page("22001", load("book_22001.html"))
        self.assertEqual(r.author, "夏目 漱石")

    def test_title_with_comma_is_kept_intact(self):
        r = bookmeter.parse_book_page("22001", load("book_22001.html"))
        self.assertEqual(r.title, "吾輩は猫である、そして犬 上巻")

    def test_old_style_gp_product_link(self):
        r = bookmeter.parse_book_page("22001", load("book_22001.html"))
        self.assertEqual(r.code_kind, "isbn10")
        self.assertEqual(r.isbn13, "9780201616224")

    def test_kindle_asin_is_not_resolved(self):
        r = bookmeter.parse_book_page("33002", load("book_33002.html"))
        self.assertEqual(r.code_kind, "asin")
        self.assertEqual(r.isbn13, "")
        self.assertFalse(r.resolved)
        self.assertTrue(any("ASIN" in n for n in r.notes))

    def test_no_amazon_link_is_reported(self):
        r = bookmeter.parse_book_page("44003", load("book_44003.html"))
        self.assertEqual(r.code_kind, "none")
        self.assertFalse(r.resolved)
        self.assertTrue(r.notes)

    def test_url_property(self):
        r = bookmeter.parse_book_page("13558368", load("book_13558368.html"))
        self.assertEqual(r.url, "https://bookmeter.com/books/13558368")


if __name__ == "__main__":
    unittest.main()
