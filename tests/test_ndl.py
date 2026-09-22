import unittest

from dokusho_import import ndl

XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"
     xmlns:dc="http://purl.org/dc/elements/1.1/"
     xmlns:dcterms="http://purl.org/dc/terms/">
  <channel>
    <item>
      <dc:title>電子版しかない本</dc:title>
      <dc:creator>著者 一郎</dc:creator>
      <dc:identifier>4297103265</dc:identifier>
      <dcterms:issued>2018-08</dcterms:issued>
    </item>
    <item>
      <dc:title>電子版しかない本 : 新装版</dc:title>
      <dc:creator>著者 一郎</dc:creator>
      <dc:identifier>978-0-201-61622-4</dc:identifier>
      <dcterms:issued>2023-04-20</dcterms:issued>
    </item>
    <item>
      <dc:title>まったく別の本</dc:title>
      <dc:identifier>9784297103262</dc:identifier>
      <dcterms:issued>2030-01-01</dcterms:issued>
    </item>
    <item>
      <dc:title>ISBNのない資料</dc:title>
      <dcterms:issued>2025-01-01</dcterms:issued>
    </item>
  </channel>
</rss>
"""


class TestNdl(unittest.TestCase):
    def setUp(self):
        self.candidates = ndl.parse_candidates(XML)

    def test_skips_items_without_isbn(self):
        self.assertEqual(len(self.candidates), 3)
        self.assertTrue(all(c.isbn13 for c in self.candidates))

    def test_normalizes_hyphenated_isbn13(self):
        self.assertIn("9780201616224", [c.isbn13 for c in self.candidates])

    def test_converts_isbn10_identifier(self):
        self.assertIn("9784297103262", [c.isbn13 for c in self.candidates])

    def test_picks_latest_matching_edition(self):
        # タイトル一致する2件のうち、出版日が新しい新装版を採る
        picked = ndl.pick_latest(self.candidates, "電子版しかない本")
        self.assertEqual(picked.isbn13, "9780201616224")
        self.assertEqual(picked.issued, "2023-04-20")

    def test_unrelated_newer_item_is_not_picked(self):
        picked = ndl.pick_latest(self.candidates, "電子版しかない本")
        self.assertNotEqual(picked.title, "まったく別の本")

    def test_build_url_encodes_japanese_and_omits_empty_creator(self):
        url = ndl.build_url("夏目 漱石の本", "")
        self.assertIn("title=", url)
        self.assertNotIn("creator=", url)
        self.assertTrue(url.startswith(ndl.ENDPOINT))

    def test_no_candidates_returns_none(self):
        self.assertIsNone(ndl.pick_latest([], "なにか"))


if __name__ == "__main__":
    unittest.main()
