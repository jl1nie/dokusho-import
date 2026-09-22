"""--save-html で保存したHTMLを、そのまま --html-dir で読み直せること。

オンラインで1回流したものを、ネットワークなしで再現できる保証。
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dokusho_import.cli import LocalSource, RemoteSource

FIXTURES = Path(__file__).parent / "fixtures"


class StubFetcher:
    """読書メーターの代わりにフィクスチャを返す。ネットワークに出ない。"""

    def __init__(self):
        self.requests_made = 0
        self.urls = []

    def get(self, url, cache_key=None):
        self.urls.append(url)
        self.requests_made += 1
        if "/books/read" in url:
            page = url.rsplit("page=", 1)[1]
            return (FIXTURES / f"read_page_{page}.html").read_text(encoding="utf-8")
        if "/books/" in url:
            book_id = url.rsplit("/", 1)[1]
            return (FIXTURES / f"book_{book_id}.html").read_text(encoding="utf-8")
        return (FIXTURES / "user.html").read_text(encoding="utf-8")


class TestSaveHtml(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name) / "saved"
        self.fetcher = StubFetcher()
        self.remote = RemoteSource("621778", self.fetcher, save_dir=self.dir)

    def test_builds_expected_urls(self):
        self.remote.read_list(1)
        self.remote.book("13558368")
        self.remote.user_page()
        self.assertEqual(
            self.fetcher.urls,
            [
                "https://bookmeter.com/users/621778/books/read?page=1",
                "https://bookmeter.com/books/13558368",
                "https://bookmeter.com/users/621778",
            ],
        )

    def test_saved_files_are_readable_by_local_source(self):
        self.remote.read_list(1)
        self.remote.book("13558368")
        self.remote.user_page()
        local = LocalSource(self.dir)
        self.assertIn("/books/13558368", local.read_list(1))
        self.assertIn("4297103265", local.book("13558368"))
        self.assertIn("読んだ本", local.user_page())

    def test_saved_bytes_match_fetched_bytes(self):
        original = self.remote.book("22001")
        self.assertEqual((self.dir / "book_22001.html").read_text(encoding="utf-8"), original)

    def test_no_save_dir_means_no_files(self):
        remote = RemoteSource("621778", StubFetcher())
        remote.book("13558368")  # 例外にならないこと
        self.assertFalse(self.dir.exists() and list(self.dir.iterdir()))


if __name__ == "__main__":
    unittest.main()
