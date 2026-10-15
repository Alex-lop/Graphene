import unittest

from src.invoice import total, total_cents


class InvoiceTest(unittest.TestCase):
    def test_whole_dollars(self):
        self.assertEqual(total([(2, "5.00")]), "$10.00")

    def test_no_cent_is_lost(self):
        self.assertEqual(total_cents([(1, "0.29")]), 29)
        self.assertEqual(total([(3, "19.99"), (1, "0.57")]), "$60.54")
