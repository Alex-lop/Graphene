import unittest

from src.export import export


class ExportTest(unittest.TestCase):
    def test_amount(self):
        self.assertEqual(export([{"id": 1, "cents": 99}])[0]["amount"], 99)
