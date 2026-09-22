import unittest

from dokusho_import import isbn


class TestIsbn(unittest.TestCase):
    def test_valid_isbn10(self):
        self.assertTrue(isbn.is_valid_isbn10("4297103265"))
        self.assertTrue(isbn.is_valid_isbn10("4-297-10326-5"))
        self.assertTrue(isbn.is_valid_isbn10("020161622X"))

    def test_rejects_bad_check_digit(self):
        self.assertFalse(isbn.is_valid_isbn10("4297103264"))
        self.assertFalse(isbn.is_valid_isbn10("1234567890"))

    def test_isbn10_to_13(self):
        self.assertEqual(isbn.isbn10_to_13("4297103265"), "9784297103262")
        self.assertEqual(isbn.isbn10_to_13("020161622X"), "9780201616224")
        self.assertTrue(isbn.is_valid_isbn13(isbn.isbn10_to_13("020161622X")))

    def test_isbn13_check_digit(self):
        self.assertTrue(isbn.is_valid_isbn13("9784297103262"))
        self.assertFalse(isbn.is_valid_isbn13("9784297103263"))
        self.assertFalse(isbn.is_valid_isbn13("1234567890123"))

    def test_classify(self):
        self.assertEqual(isbn.classify("4297103265"), ("isbn10", "9784297103262"))
        self.assertEqual(isbn.classify("9784297103262"), ("isbn13", "9784297103262"))
        self.assertEqual(isbn.classify("B08XYZ1234"), ("asin", ""))
        self.assertEqual(isbn.classify("4297103264"), ("unknown", ""))
        self.assertEqual(isbn.classify(""), ("unknown", ""))

    def test_asin_not_mistaken_for_isbn(self):
        # ASINはISBN扱いしない
        self.assertFalse(isbn.is_valid_isbn10("B00ABCDEFG"))
        self.assertTrue(isbn.is_asin("B00ABCDEFG"))


if __name__ == "__main__":
    unittest.main()
