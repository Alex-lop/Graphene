import unittest

from prices.parse import parse_price


class ParseTest(unittest.TestCase):
    def test_symbols(self):
        self.assertEqual(parse_price("$12.50"), ("USD", 1250))
        self.assertEqual(parse_price("€0.99"), ("EUR", 99))
        self.assertEqual(parse_price(" £3 "), ("GBP", 300))

    def test_swiss_francs(self):
        self.assertEqual(parse_price("CHF 12.50"), ("CHF", 1250))
